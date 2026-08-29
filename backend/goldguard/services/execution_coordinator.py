from __future__ import annotations

import asyncio
import hashlib
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal

from goldguard.broker.paper_portfolio import PaperPortfolioBroker
from goldguard.domain.enums import (
    ExecutionMode,
    MarginMode,
    OrderSide,
    OrderType,
    PositionSide,
    ProductKind,
)
from goldguard.domain.models import Candle, Quote
from goldguard.execution.models import (
    ExecutionResult,
    MarketScope,
    OrderIntent,
    ProtectionPlan,
)
from goldguard.storage.database import Database
from goldguard.storage.execution_repository import ExecutionRepository


@dataclass(frozen=True, slots=True)
class DecisionOutcome:
    action: str  # "ENTER", "EXIT", "STOP", "HOLD"
    intent_created: bool = False
    intent: OrderIntent | None = None
    result: ExecutionResult | None = None
    reason: str = ""


@dataclass(frozen=True, slots=True)
class EntryPlan:
    approved: bool
    reason: str
    side: OrderSide = OrderSide.BUY
    position_side: PositionSide = PositionSide.LONG
    quantity: Decimal = Decimal("0")
    leverage: int = 1
    stop_loss_price: Decimal | None = None
    take_profit_price: Decimal | None = None


EntryPlanner = Callable[[MarketScope, Candle], EntryPlan]


def decision_key(mode: ExecutionMode, scope: MarketScope, close_time: datetime) -> str:
    material = f"{mode.value}|{scope.product.value}|{scope.symbol}|{close_time.isoformat()}"
    return hashlib.sha256(material.encode()).hexdigest()[:16]


class ExecutionCoordinator:
    def __init__(
        self,
        broker: PaperPortfolioBroker,
        repository: ExecutionRepository,
        database: Database,
        entry_planner: EntryPlanner | None = None,
    ) -> None:
        self.broker = broker
        self.repository = repository
        self.database = database
        self._entry_planner = entry_planner
        self._entries_paused = False
        self._lock = asyncio.Lock()

    def pause_entries(self) -> None:
        self._entries_paused = True

    def resume_entries(self) -> None:
        self._entries_paused = False

    async def evaluate(self, scope: MarketScope, candle: Candle) -> DecisionOutcome:
        if self._entries_paused:
            return DecisionOutcome(action="HOLD", reason="entries_paused")
        if self._entry_planner is None:
            return DecisionOutcome(action="HOLD", reason="entry_planner_unconfigured")

        plan = self._entry_planner(scope, candle)
        if not plan.approved:
            return DecisionOutcome(action="HOLD", reason=plan.reason)
        if plan.quantity <= 0:
            return DecisionOutcome(action="HOLD", reason="entry_plan_quantity_invalid")
        if plan.stop_loss_price is None or plan.take_profit_price is None:
            return DecisionOutcome(action="HOLD", reason="entry_plan_protection_missing")

        async with self._lock:
            # Deterministic client order ID for this candle
            candle_ts = candle.close_time.strftime("%Y%m%d%H%M")
            prod_prefix = scope.product.value[:1]
            client_id = f"gg-{prod_prefix}-{scope.symbol}-{candle_ts}"
            intent_id = f"intent-{uuid.uuid4().hex[:12]}"

            intent = OrderIntent(
                intent_id=intent_id,
                client_order_id=client_id,
                mode=scope.mode,
                product=scope.product,
                symbol=scope.symbol,
                side=plan.side,
                position_side=plan.position_side,
                order_type=OrderType.MARKET,
                quantity=plan.quantity,
                price=candle.close,
                margin_mode=MarginMode.ISOLATED,
                leverage=plan.leverage if scope.product == ProductKind.FUTURES else 1,
            )

            saved_intent, created = self.repository.create_intent_once(intent)
            if not created:
                return DecisionOutcome(
                    action="HOLD",
                    intent_created=False,
                    intent=saved_intent,
                    reason="duplicate_intent",
                )

            res = await self.broker.submit(saved_intent)
            if res.order is not None:
                self.repository.save_order(res.order)
            if res.position is not None:
                self.repository.save_position(res.position)
                protection = ProtectionPlan(
                    position_id=res.position.position_id,
                    stop_loss_price=plan.stop_loss_price,
                    take_profit_price=plan.take_profit_price,
                )
                self.broker.install_protection(protection)
                self.repository.save_protection(protection)

            return DecisionOutcome(
                action="ENTER",
                intent_created=True,
                intent=saved_intent,
                result=res,
                reason="signal_executed",
            )

    async def manage_positions(self, scope: MarketScope, quote: Quote) -> DecisionOutcome:
        mid_price = (quote.bid + quote.ask) / Decimal("2")
        results = await self.broker.process_price(scope.product, scope.symbol, mid_price)
        if not results:
            return DecisionOutcome(action="HOLD", reason="no_exit_triggered")
        result = results[0]
        if result.order is not None:
            self.repository.ensure_intent_for_order(result.order)
            self.repository.save_order(result.order)
        if result.position is not None:
            self.repository.save_position(result.position)
            self.repository.delete_protection(result.position.position_id)
        return DecisionOutcome(
            action="STOP",
            result=result,
            reason="protection_triggered",
        )
