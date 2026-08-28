from dataclasses import dataclass
from decimal import ROUND_DOWN, Decimal

from goldguard.domain.defaults import StrategySettings
from goldguard.domain.models import TradePlan
from goldguard.market.binance import SymbolFilters


@dataclass(frozen=True)
class RiskContext:
    equity: Decimal
    available_cash: Decimal
    entry: Decimal
    atr: Decimal
    fee_rate: Decimal
    filters: SymbolFilters
    rolling_24h_loss_rate: Decimal
    peak_drawdown_rate: Decimal
    consecutive_losses: int
    minutes_since_exit: int
    open_positions: int
    data_healthy: bool
    spread_acceptable: bool
    event_blackout: bool
    lease_owned: bool
    # Autonomy kill switches & genome provenance
    promotion_churn: int = 0
    quota_exhausted: bool = False
    gateway_degraded: bool = False
    genome_status: str = "active"
    genome_hash: str = ""


@dataclass(frozen=True)
class RiskDecision:
    approved: bool
    reason_codes: tuple[str, ...]
    plan: TradePlan | None = None
    genome_hash: str = ""


def floor_to_increment(value: Decimal, increment: Decimal) -> Decimal:
    if increment <= 0:
        raise ValueError("rounding increment must be positive")
    steps = (value / increment).to_integral_value(rounding=ROUND_DOWN)
    return steps * increment


class RiskEngine:
    def __init__(self, settings: StrategySettings) -> None:
        self.settings = settings

    def plan_entry(self, context: RiskContext) -> RiskDecision:
        blocked = self._blocked_reason(context)
        if blocked is not None:
            return RiskDecision(False, (blocked,), genome_hash=context.genome_hash)
        if min(context.equity, context.available_cash, context.entry, context.atr) <= 0:
            return RiskDecision(
                False, ("INVALID_ACCOUNT_OR_MARKET_VALUE",), genome_hash=context.genome_hash
            )

        raw_distance = context.atr * self.settings.stop_atr_multiple
        minimum_distance = context.entry * self.settings.minimum_stop_rate
        maximum_distance = context.entry * self.settings.maximum_stop_rate
        distance = min(max(raw_distance, minimum_distance), maximum_distance)
        stop = floor_to_increment(context.entry - distance, context.filters.tick_size)
        actual_distance = context.entry - stop
        if actual_distance <= 0:
            return RiskDecision(False, ("INVALID_STOP_DISTANCE",), genome_hash=context.genome_hash)

        risk_budget = context.equity * self.settings.risk_per_trade
        quantity_by_risk = risk_budget / actual_distance
        entry_with_fee = context.entry * (Decimal("1") + context.fee_rate)
        cash_budget = context.available_cash * self.settings.cash_utilization
        quantity_by_cash = cash_budget / entry_with_fee
        unrounded_quantity = min(
            quantity_by_risk,
            quantity_by_cash,
            context.filters.maximum_quantity,
        )
        quantity = floor_to_increment(unrounded_quantity, context.filters.step_size)
        if quantity < context.filters.minimum_quantity or quantity <= 0:
            return RiskDecision(False, ("BELOW_MINIMUM_QUANTITY",), genome_hash=context.genome_hash)
        if quantity * context.entry < context.filters.minimum_notional:
            return RiskDecision(False, ("BELOW_MINIMUM_NOTIONAL",), genome_hash=context.genome_hash)
        actual_risk = quantity * actual_distance
        if actual_risk > risk_budget:
            capped = floor_to_increment(risk_budget / actual_distance, context.filters.step_size)
            if capped < context.filters.minimum_quantity or capped * context.entry < context.filters.minimum_notional:
                return RiskDecision(False, ("INSUFFICIENT_CASH_FOR_RISK",), genome_hash=context.genome_hash)
            quantity = capped
            actual_risk = quantity * actual_distance
        if actual_risk > risk_budget:
            return RiskDecision(False, ("RISK_BUDGET_EXCEEDED",), genome_hash=context.genome_hash)
        target_unrounded = context.entry + (actual_distance * self.settings.reward_r_multiple)
        target = floor_to_increment(target_unrounded, context.filters.tick_size)
        expected_fees = quantity * context.entry * context.fee_rate * Decimal("2")
        plan = TradePlan(
            entry=context.entry,
            stop=stop,
            target=target,
            quantity=quantity,
            risk_amount=actual_risk,
            expected_fees=expected_fees,
        )
        return RiskDecision(True, ("RISK_APPROVED",), plan, genome_hash=context.genome_hash)

    def _blocked_reason(self, context: RiskContext) -> str | None:
        # Autonomy & System Kill Switches
        if context.genome_status != "active":
            return "GENOME_NOT_ACTIVE"
        if context.gateway_degraded:
            return "GATEWAY_DEGRADED"
        if context.quota_exhausted:
            return "RESEARCH_QUOTA_EXHAUSTED"
        if context.promotion_churn >= 3:
            return "PROMOTION_CHURN_HALT"

        # Risk and Market Gates
        if context.peak_drawdown_rate >= self.settings.emergency_drawdown_halt:
            return "EMERGENCY_DRAWDOWN_HALT"
        if context.rolling_24h_loss_rate >= self.settings.daily_loss_halt:
            return "DAILY_LOSS_HALT"
        if context.consecutive_losses >= self.settings.consecutive_loss_limit:
            return "LOSS_STREAK_COOLDOWN"
        if context.minutes_since_exit < self.settings.cooldown_minutes:
            return "POST_EXIT_COOLDOWN"
        if context.open_positions >= self.settings.maximum_positions:
            return "POSITION_LIMIT"
        if not context.data_healthy:
            return "DATA_UNHEALTHY"
        if not context.spread_acceptable:
            return "SPREAD_TOO_WIDE"
        if context.event_blackout:
            return "MACRO_EVENT_BLACKOUT"
        if not context.lease_owned:
            return "WORKER_LEASE_MISSING"
        return None
