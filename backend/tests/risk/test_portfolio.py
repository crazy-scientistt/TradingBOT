from __future__ import annotations

from decimal import Decimal

from goldguard.domain.enums import ExecutionMode, ProductKind
from goldguard.domain.profile import default_autonomous_profile
from goldguard.execution.models import MarketScope
from goldguard.risk.costs import estimate_costs
from goldguard.risk.portfolio import (
    PortfolioRiskSnapshot,
    evaluate_portfolio_entry,
)


def test_approved_capital_never_exceeds_user_ceiling() -> None:
    profile = default_autonomous_profile()
    # profile risk max_capital_per_trade_rate = 0.005 (0.5%)
    snapshot = PortfolioRiskSnapshot(
        total_equity_usdt=Decimal("10000.00"),
        available_cash_usdt=Decimal("5000.00"),
        used_margin_usdt=Decimal("0"),
        total_notional_exposure_usdt=Decimal("0"),
        rolling_24h_loss_rate=Decimal("0"),
        open_positions_count=0,
    )
    scope = MarketScope(mode=ExecutionMode.PAPER, product=ProductKind.FUTURES, symbol="BTCUSDT")
    costs = estimate_costs(ProductKind.FUTURES, gross_edge=Decimal("0.02"))

    # Request $500 notional at 1x -> $500 capital requested, max allowed is $10000 * 0.005 = $50
    decision = evaluate_portfolio_entry(
        profile=profile,
        snapshot=snapshot,
        scope=scope,
        requested_edge=Decimal("0.02"),
        cost=costs,
        requested_notional=Decimal("500.00"),
        requested_leverage=1,
    )
    assert decision.approved is True
    assert decision.capital_usdt == Decimal("50.00")
    max_allowed = snapshot.total_equity_usdt * profile.risk.max_capital_per_trade_rate
    assert decision.capital_usdt <= max_allowed


def test_portfolio_rejects_daily_loss_limit_exceeded() -> None:
    profile = default_autonomous_profile()
    # profile risk limit is 0.03 (3%)
    snapshot = PortfolioRiskSnapshot(
        total_equity_usdt=Decimal("10000.00"),
        available_cash_usdt=Decimal("5000.00"),
        used_margin_usdt=Decimal("0"),
        total_notional_exposure_usdt=Decimal("0"),
        rolling_24h_loss_rate=Decimal("0.035"),
        open_positions_count=0,
    )
    scope = MarketScope(mode=ExecutionMode.PAPER, product=ProductKind.SPOT, symbol="PAXGUSDT")
    costs = estimate_costs(ProductKind.SPOT, gross_edge=Decimal("0.02"))

    decision = evaluate_portfolio_entry(
        profile=profile,
        snapshot=snapshot,
        scope=scope,
        requested_edge=Decimal("0.02"),
        cost=costs,
        requested_notional=Decimal("50.00"),
    )
    assert decision.approved is False
    assert decision.reason_code == "DAILY_LOSS_LIMIT_EXCEEDED"

