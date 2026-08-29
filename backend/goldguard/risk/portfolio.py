from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from goldguard.domain.enums import ProductKind
from goldguard.domain.profile import AutonomousProfile
from goldguard.execution.models import MarketScope
from goldguard.risk.costs import CostEstimate


@dataclass(frozen=True, slots=True)
class PortfolioRiskSnapshot:
    total_equity_usdt: Decimal
    available_cash_usdt: Decimal
    used_margin_usdt: Decimal
    total_notional_exposure_usdt: Decimal
    rolling_24h_loss_rate: Decimal
    open_positions_count: int


@dataclass(frozen=True, slots=True)
class PortfolioDecision:
    approved: bool
    reason_code: str
    capital_usdt: Decimal = Decimal("0")
    notional_usdt: Decimal = Decimal("0")
    leverage: int = 1
    estimated_cost: CostEstimate | None = None


def evaluate_portfolio_entry(
    profile: AutonomousProfile,
    snapshot: PortfolioRiskSnapshot,
    scope: MarketScope,
    requested_edge: Decimal,
    cost: CostEstimate,
    requested_notional: Decimal,
    requested_leverage: int = 1,
) -> PortfolioDecision:
    # 1. Check daily rolling loss limit
    if snapshot.rolling_24h_loss_rate >= profile.risk.rolling_24h_loss_limit_rate:
        return PortfolioDecision(
            approved=False,
            reason_code="DAILY_LOSS_LIMIT_EXCEEDED",
            estimated_cost=cost,
        )

    # 2. Check cost buffer and positive net edge
    if not cost.is_profitable:
        return PortfolioDecision(
            approved=False,
            reason_code="NET_EDGE_BELOW_COST_BUFFER",
            estimated_cost=cost,
        )

    # 3. Check leverage bound
    max_lev = profile.risk.max_futures_leverage if scope.product == ProductKind.FUTURES else 1
    actual_leverage = min(requested_leverage, max_lev)

    # 4. Check capital limit per trade
    required_capital = requested_notional / Decimal(str(actual_leverage))
    max_capital_allowed = snapshot.total_equity_usdt * profile.risk.max_capital_per_trade_rate
    if required_capital > max_capital_allowed:
        # Clamp capital to user ceiling
        required_capital = max_capital_allowed
        requested_notional = required_capital * Decimal(str(actual_leverage))

    # 5. Check total exposure limit
    max_total_exposure = snapshot.total_equity_usdt * profile.risk.max_total_exposure_rate
    if snapshot.total_notional_exposure_usdt + requested_notional > max_total_exposure:
        available_notional = max_total_exposure - snapshot.total_notional_exposure_usdt
        if available_notional <= Decimal("0"):
            return PortfolioDecision(
                approved=False,
                reason_code="MAX_TOTAL_EXPOSURE_EXCEEDED",
                estimated_cost=cost,
            )
        requested_notional = available_notional
        required_capital = requested_notional / Decimal(str(actual_leverage))

    # 6. Check wallet balance
    if required_capital > snapshot.available_cash_usdt:
        return PortfolioDecision(
            approved=False,
            reason_code="INSUFFICIENT_AVAILABLE_BALANCE",
            estimated_cost=cost,
        )

    return PortfolioDecision(
        approved=True,
        reason_code="RISK_APPROVED",
        capital_usdt=required_capital,
        notional_usdt=requested_notional,
        leverage=actual_leverage,
        estimated_cost=cost,
    )

