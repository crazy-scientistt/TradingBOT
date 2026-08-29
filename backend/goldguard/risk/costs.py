from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from goldguard.domain.enums import ProductKind


@dataclass(frozen=True, slots=True)
class CostEstimate:
    gross_edge: Decimal
    fees: Decimal
    spread: Decimal
    slippage: Decimal
    funding: Decimal = Decimal("0")
    uncertainty_buffer: Decimal = Decimal("0.0001")

    @property
    def total_cost(self) -> Decimal:
        return self.fees + self.spread + self.slippage + self.funding + self.uncertainty_buffer

    @property
    def net_edge(self) -> Decimal:
        return self.gross_edge - self.total_cost

    @property
    def is_profitable(self) -> bool:
        return self.net_edge > Decimal("0")


def estimate_costs(
    product: ProductKind,
    gross_edge: Decimal,
    fee_rate: Decimal = Decimal("0.001"),
    spread_rate: Decimal = Decimal("0.0005"),
    slippage_rate: Decimal = Decimal("0.0002"),
    funding_rate: Decimal = Decimal("0"),
    uncertainty_buffer: Decimal = Decimal("0.0001"),
) -> CostEstimate:
    # Round-trip fees (entry + exit)
    fees = fee_rate * Decimal("2")
    spread = spread_rate
    slippage = slippage_rate * Decimal("2")
    funding = funding_rate if product == ProductKind.FUTURES else Decimal("0")

    return CostEstimate(
        gross_edge=gross_edge,
        fees=fees,
        spread=spread,
        slippage=slippage,
        funding=funding,
        uncertainty_buffer=uncertainty_buffer,
    )

