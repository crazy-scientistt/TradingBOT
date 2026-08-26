from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Protocol

from goldguard.domain.enums import ExitReason, OrderSide
from goldguard.domain.models import Quote, TradePlan


@dataclass(frozen=True)
class PaperFill:
    client_order_id: str
    side: OrderSide
    quantity: Decimal
    price: Decimal
    fee: Decimal
    filled_at: datetime

    @property
    def gross_value(self) -> Decimal:
        return self.quantity * self.price


@dataclass(frozen=True)
class PaperPosition:
    plan: TradePlan
    entry_fill: PaperFill

    @property
    def quantity(self) -> Decimal:
        return self.entry_fill.quantity


@dataclass(frozen=True)
class ClosedPaperTrade:
    entry_fill: PaperFill
    exit_fill: PaperFill
    exit_reason: ExitReason
    realized_pnl: Decimal


class Broker(Protocol):
    @property
    def cash(self) -> Decimal: ...

    @property
    def position(self) -> PaperPosition | None: ...

    def open_long(
        self,
        plan: TradePlan,
        quote: Quote,
        *,
        client_order_id: str,
    ) -> PaperFill: ...

    def exit_long(
        self,
        quote: Quote,
        *,
        client_order_id: str,
        reason: ExitReason,
    ) -> ClosedPaperTrade: ...
