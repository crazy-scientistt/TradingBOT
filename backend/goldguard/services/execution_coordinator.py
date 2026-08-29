from __future__ import annotations

import asyncio
import hashlib
import uuid
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


def decision_key(mode: ExecutionMode, scope: MarketScope, close_time: datetime) -> str:
    material = f"{mode.value}|{scope.product.value}|{scope.symbol}|{close_time.isoformat()}"
    return hashlib.sha256(material.encode()).hexdigest()[:16]


class ExecutionCoordinator:
    def __init__(
        self,
        broker: PaperPortfolioBroker,
        repository: ExecutionRepository,
        database: Database,
    ) -> None:
        self.broker = broker
        self.repository = repository
        self.database = database
        self._entries_paused = False
        self._lock = asyncio.Lock()

    def pause_entries(self) -> None:
        self._entries_paused = True

    def resume_entries(self) -> None:
        self._entries_paused = False

    async def evaluate(self, scope: MarketScope, candle: Candle) -> DecisionOutcome:
        if self._entries_paused:
            return DecisionOutcome(action="HOLD", reason="entries_paused")

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
                side=OrderSide.BUY,
                position_side=PositionSide.LONG,
                order_type=OrderType.MARKET,
                quantity=Decimal("0.01"),
                price=candle.close,
                margin_mode=MarginMode.ISOLATED,
                leverage=5 if scope.product == ProductKind.FUTURES else 1,
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

            return DecisionOutcome(
                action="ENTER",
                intent_created=True,
                intent=saved_intent,
                result=res,
                reason="signal_executed",
            )

    async def manage_positions(self, scope: MarketScope, quote: Quote) -> DecisionOutcome:
        broker = self.broker.spot if scope.product == ProductKind.SPOT else self.broker.futures
        mid_price = (quote.bid + quote.ask) / Decimal("2")
        broker.on_price(scope.symbol, mid_price)
        return DecisionOutcome(action="STOP", reason="position_managed")

