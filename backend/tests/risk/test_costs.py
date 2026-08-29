from __future__ import annotations

from decimal import Decimal

from goldguard.domain.enums import ProductKind
from goldguard.risk.costs import estimate_costs


def test_cost_estimation_spot() -> None:
    # 0.5% gross edge
    costs = estimate_costs(
        product=ProductKind.SPOT,
        gross_edge=Decimal("0.0050"),
        fee_rate=Decimal("0.0010"),
        spread_rate=Decimal("0.0005"),
        slippage_rate=Decimal("0.0002"),
    )
    # total cost = 0.0020 (fees) + 0.0005 (spread) + 0.0004 (slippage) + 0.0001 (buffer) = 0.0030
    assert costs.total_cost == Decimal("0.0030")
    assert costs.net_edge == Decimal("0.0020")
    assert costs.is_profitable is True


def test_micro_trade_rejects_edge_below_total_cost() -> None:
    # 0.04% gross edge (less than 0.3% total cost)
    costs = estimate_costs(
        product=ProductKind.FUTURES,
        gross_edge=Decimal("0.0004"),
        fee_rate=Decimal("0.0005"),
        spread_rate=Decimal("0.0005"),
        slippage_rate=Decimal("0.0002"),
    )
    assert costs.is_profitable is False
    assert costs.net_edge < Decimal("0")

