from datetime import datetime
from decimal import Decimal

from goldguard.broker.base import ClosedPaperTrade, PaperFill, PaperPosition
from goldguard.domain.enums import ExitReason, OrderSide
from goldguard.domain.models import Candle, Quote, TradePlan


class PaperOrderRejected(RuntimeError):
    """A paper order that cannot be applied atomically."""


class PaperBroker:
    """A deterministic, long-only broker with conservative fill assumptions."""

    def __init__(
        self,
        starting_cash: Decimal,
        fee_rate: Decimal,
        slippage_rate: Decimal,
    ) -> None:
        if starting_cash <= 0:
            raise ValueError("starting paper cash must be positive")
        if fee_rate < 0 or slippage_rate < 0:
            raise ValueError("fee and slippage rates cannot be negative")
        self._cash = starting_cash
        self._fee_rate = fee_rate
        self._slippage_rate = slippage_rate
        self._position: PaperPosition | None = None
        self._fills: list[PaperFill] = []
        self._order_results: dict[str, PaperFill | ClosedPaperTrade] = {}

    @property
    def cash(self) -> Decimal:
        return self._cash

    @property
    def position(self) -> PaperPosition | None:
        return self._position

    @property
    def fills(self) -> tuple[PaperFill, ...]:
        return tuple(self._fills)

    def equity(self, quote: Quote) -> Decimal:
        if self._position is None:
            return self._cash
        return self._cash + self._position.quantity * quote.bid

    def open_long(
        self,
        plan: TradePlan,
        quote: Quote,
        *,
        client_order_id: str,
    ) -> PaperFill:
        prior = self._order_results.get(client_order_id)
        if prior is not None:
            if not isinstance(prior, PaperFill) or prior.side is not OrderSide.BUY:
                raise PaperOrderRejected("client order id already used")
            return prior
        self._validate_order_id(client_order_id)
        if self._position is not None:
            raise PaperOrderRejected("position already open")

        price = quote.ask * (Decimal("1") + self._slippage_rate)
        gross = price * plan.quantity
        fee = gross * self._fee_rate
        total = gross + fee
        if total > self._cash:
            raise PaperOrderRejected("insufficient paper cash")

        fill = PaperFill(
            client_order_id=client_order_id,
            side=OrderSide.BUY,
            quantity=plan.quantity,
            price=price,
            fee=fee,
            filled_at=quote.observed_at,
        )
        self._cash -= total
        self._position = PaperPosition(plan=plan, entry_fill=fill)
        self._fills.append(fill)
        self._order_results[client_order_id] = fill
        return fill

    def exit_long(
        self,
        quote: Quote,
        *,
        client_order_id: str,
        reason: ExitReason,
    ) -> ClosedPaperTrade:
        return self._exit_at(
            reference_price=quote.bid,
            filled_at=quote.observed_at,
            client_order_id=client_order_id,
            reason=reason,
        )

    def process_candle(
        self,
        candle: Candle,
        *,
        client_order_id: str,
    ) -> ClosedPaperTrade | None:
        prior = self._order_results.get(client_order_id)
        if prior is not None:
            if not isinstance(prior, ClosedPaperTrade):
                raise PaperOrderRejected("client order id already used")
            return prior
        if self._position is None:
            return None

        plan = self._position.plan
        if candle.low <= plan.stop:
            reference = candle.open if candle.open < plan.stop else plan.stop
            return self._exit_at(
                reference_price=reference,
                filled_at=candle.close_time,
                client_order_id=client_order_id,
                reason=ExitReason.STOP_LOSS,
            )
        if candle.high >= plan.target:
            reference = candle.open if candle.open > plan.target else plan.target
            return self._exit_at(
                reference_price=reference,
                filled_at=candle.close_time,
                client_order_id=client_order_id,
                reason=ExitReason.TAKE_PROFIT,
            )
        return None

    def _exit_at(
        self,
        *,
        reference_price: Decimal,
        filled_at: datetime,
        client_order_id: str,
        reason: ExitReason,
    ) -> ClosedPaperTrade:
        prior = self._order_results.get(client_order_id)
        if prior is not None:
            if not isinstance(prior, ClosedPaperTrade):
                raise PaperOrderRejected("client order id already used")
            return prior
        self._validate_order_id(client_order_id)
        if self._position is None:
            raise PaperOrderRejected("no position to exit")

        position = self._position
        price = reference_price * (Decimal("1") - self._slippage_rate)
        gross = price * position.quantity
        fee = gross * self._fee_rate
        exit_fill = PaperFill(
            client_order_id=client_order_id,
            side=OrderSide.SELL,
            quantity=position.quantity,
            price=price,
            fee=fee,
            filled_at=filled_at,
        )
        realized_pnl = gross - fee - position.entry_fill.gross_value - position.entry_fill.fee
        trade = ClosedPaperTrade(
            entry_fill=position.entry_fill,
            exit_fill=exit_fill,
            exit_reason=reason,
            realized_pnl=realized_pnl,
        )
        self._cash += gross - fee
        self._position = None
        self._fills.append(exit_fill)
        self._order_results[client_order_id] = trade
        return trade

    @staticmethod
    def _validate_order_id(client_order_id: str) -> None:
        if not client_order_id.strip():
            raise PaperOrderRejected("client order id is required")
