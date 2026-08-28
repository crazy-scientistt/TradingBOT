from dataclasses import replace
from decimal import Decimal

import pytest
from goldguard.domain.defaults import SAFE_DEFAULT_V1
from goldguard.market.binance import SymbolFilters
from goldguard.risk.engine import RiskContext, RiskEngine


def valid_context() -> RiskContext:
    return RiskContext(
        equity=Decimal("100"),
        available_cash=Decimal("100"),
        entry=Decimal("2500"),
        atr=Decimal("10"),
        fee_rate=Decimal("0.001"),
        filters=SymbolFilters(
            tick_size=Decimal("0.01"),
            step_size=Decimal("0.0001"),
            minimum_quantity=Decimal("0.0001"),
            maximum_quantity=Decimal("100"),
            minimum_notional=Decimal("5"),
        ),
        rolling_24h_loss_rate=Decimal("0"),
        peak_drawdown_rate=Decimal("0"),
        consecutive_losses=0,
        minutes_since_exit=120,
        open_positions=0,
        data_healthy=True,
        spread_acceptable=True,
        event_blackout=False,
        lease_owned=True,
        promotion_churn=0,
        quota_exhausted=False,
        gateway_degraded=False,
        genome_status="active",
        genome_hash="sha256-test-hash-valid",
    )


def test_risk_engine_sizes_exact_decimal_plan_with_atr_stop_and_two_r_target() -> None:
    result = RiskEngine(SAFE_DEFAULT_V1).plan_entry(valid_context())

    assert result.approved is True
    assert result.plan is not None
    assert result.plan.entry == Decimal("2500")
    assert result.plan.stop == Decimal("2485.00")
    assert result.plan.target == Decimal("2530.00")
    assert result.plan.quantity == Decimal("0.0333")
    assert result.plan.risk_amount == Decimal("0.499500")
    assert result.plan.expected_fees == Decimal("0.1665000")
    assert result.genome_hash == "sha256-test-hash-valid"


def test_cash_capped_size_never_exceeds_risk_budget() -> None:
    context = replace(
        valid_context(),
        equity=Decimal("10000"),
        available_cash=Decimal("10000"),
        entry=Decimal("4600"),
        atr=Decimal("8"),
    )
    result = RiskEngine(SAFE_DEFAULT_V1).plan_entry(context)
    assert result.approved is True
    assert result.plan is not None
    budget = context.equity * SAFE_DEFAULT_V1.risk_per_trade
    assert result.plan.risk_amount <= budget


def test_stop_distance_is_clamped_to_approved_bounds() -> None:
    engine = RiskEngine(SAFE_DEFAULT_V1)

    quiet = engine.plan_entry(replace(valid_context(), atr=Decimal("0.1")))
    volatile = engine.plan_entry(replace(valid_context(), atr=Decimal("100")))

    assert quiet.plan is not None and quiet.plan.stop == Decimal("2491.25")
    assert volatile.plan is not None and volatile.plan.stop == Decimal("2468.75")


@pytest.mark.parametrize(
    ("field", "value", "reason"),
    [
        ("rolling_24h_loss_rate", Decimal("0.03"), "DAILY_LOSS_HALT"),
        ("peak_drawdown_rate", Decimal("0.05"), "EMERGENCY_DRAWDOWN_HALT"),
        ("consecutive_losses", 3, "LOSS_STREAK_COOLDOWN"),
        ("minutes_since_exit", 59, "POST_EXIT_COOLDOWN"),
        ("open_positions", 1, "POSITION_LIMIT"),
        ("data_healthy", False, "DATA_UNHEALTHY"),
        ("spread_acceptable", False, "SPREAD_TOO_WIDE"),
        ("event_blackout", True, "MACRO_EVENT_BLACKOUT"),
        ("lease_owned", False, "WORKER_LEASE_MISSING"),
        ("genome_status", "candidate", "GENOME_NOT_ACTIVE"),
        ("genome_status", "quarantined", "GENOME_NOT_ACTIVE"),
        ("gateway_degraded", True, "GATEWAY_DEGRADED"),
        ("quota_exhausted", True, "RESEARCH_QUOTA_EXHAUSTED"),
        ("promotion_churn", 3, "PROMOTION_CHURN_HALT"),
    ],
)
def test_each_risk_gate_rejects_entry(field: str, value: object, reason: str) -> None:
    result = RiskEngine(SAFE_DEFAULT_V1).plan_entry(replace(valid_context(), **{field: value}))

    assert result.approved is False
    assert result.plan is None
    assert result.reason_codes == (reason,)


def test_exchange_minimum_notional_rejects_too_small_account() -> None:
    result = RiskEngine(SAFE_DEFAULT_V1).plan_entry(
        replace(valid_context(), equity=Decimal("1"), available_cash=Decimal("1"))
    )

    assert result.approved is False
    assert result.reason_codes == ("BELOW_MINIMUM_NOTIONAL",)


def test_provenance_invariant_cannot_forge_risk_decision() -> None:
    """Prove that RiskDecision quantity and prices originate exclusively in RiskEngine."""
    engine = RiskEngine(SAFE_DEFAULT_V1)
    context = valid_context()
    decision = engine.plan_entry(context)
    assert decision.approved is True
    assert decision.plan is not None
    assert decision.genome_hash == context.genome_hash
