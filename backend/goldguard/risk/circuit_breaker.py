from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Any


@dataclass(frozen=True, slots=True)
class RollingLossSnapshot:
    realized_loss: Decimal  # positive = loss
    unrealized_loss: Decimal
    fees: Decimal
    funding: Decimal
    slippage: Decimal

    @property
    def total_loss_usdt(self) -> Decimal:
        return (
            self.realized_loss
            + self.unrealized_loss
            + self.fees
            + self.funding
            + self.slippage
        )


@dataclass(frozen=True, slots=True)
class BreakerResult:
    tripped: bool
    total_loss_usdt: Decimal
    reason: str = ""


class CircuitBreaker:
    def __init__(self, loss_source: Any = None) -> None:
        self.loss_source = loss_source
        self._tripped = False
        self._manual_loss: RollingLossSnapshot | None = None

    def seed_loss(
        self,
        realized: str | Decimal,
        unrealized: str | Decimal,
        fees: str | Decimal,
        funding: str | Decimal,
        slippage: str | Decimal,
    ) -> None:
        r = -Decimal(str(realized)) if Decimal(str(realized)) < 0 else Decimal(str(realized))
        u = -Decimal(str(unrealized)) if Decimal(str(unrealized)) < 0 else Decimal(str(unrealized))
        self._manual_loss = RollingLossSnapshot(
            realized_loss=r,
            unrealized_loss=u,
            fees=Decimal(str(fees)),
            funding=Decimal(str(funding)),
            slippage=Decimal(str(slippage)),
        )

    def measure(self) -> RollingLossSnapshot:
        if self._manual_loss is not None:
            return self._manual_loss
        return RollingLossSnapshot(
            realized_loss=Decimal("0"),
            unrealized_loss=Decimal("0"),
            fees=Decimal("0"),
            funding=Decimal("0"),
            slippage=Decimal("0"),
        )

    async def evaluate(self, limit_usdt: Decimal) -> BreakerResult:
        snapshot = self.measure()
        total_loss = snapshot.total_loss_usdt
        if total_loss >= limit_usdt and limit_usdt > 0:
            self._tripped = True
            return BreakerResult(
                tripped=True,
                total_loss_usdt=total_loss,
                reason=f"rolling loss {total_loss} exceeds limit {limit_usdt}",
            )
        return BreakerResult(tripped=False, total_loss_usdt=total_loss)

