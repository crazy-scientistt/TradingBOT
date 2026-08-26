from dataclasses import replace
from datetime import UTC, datetime, timedelta

import pytest
from goldguard.context.models import ContextItem, ContextSnapshot, ContextSource
from goldguard.context.playbook import ChecklistInputs, ProfessionalChecklist
from goldguard.domain.enums import ChecklistAction

NOW = datetime(2026, 8, 26, 12, tzinfo=UTC)


def fresh_context() -> ContextSnapshot:
    return ContextSnapshot.build(
        fetched_at=NOW - timedelta(minutes=5),
        sources=(
            ContextSource(
                url="https://www.federalreserve.gov/monetarypolicy/fomccalendars.htm",
                title="FOMC calendar",
                published_at=NOW - timedelta(hours=1),
            ),
        ),
        items=(
            ContextItem(
                summary="No unscheduled policy change is reported.",
                driver="rates",
                direction="neutral",
                severity="low",
                published_at=NOW - timedelta(hours=1),
                source_indexes=(0,),
                contradictory=False,
            ),
        ),
    )


def valid_inputs() -> ChecklistInputs:
    return ChecklistInputs(
        context=fresh_context(),
        now=NOW,
        data_healthy=True,
        exchange_normal=True,
        liquidity_acceptable=True,
        regime_clear=True,
        deterministic_setup=True,
        complete_trade_plan=True,
        risk_budget_available=True,
        cooldown_clear=True,
        event_blackout=False,
    )


def test_complete_professional_checklist_passes() -> None:
    result = ProfessionalChecklist(max_context_age=timedelta(minutes=30)).evaluate(valid_inputs())

    assert result.action is ChecklistAction.PASS
    assert result.reason_codes == ("PRO_CHECKLIST_PASSED",)


@pytest.mark.parametrize(
    ("field", "value", "reason"),
    [
        ("data_healthy", False, "DATA_UNHEALTHY"),
        ("exchange_normal", False, "EXCHANGE_UNHEALTHY"),
        ("liquidity_acceptable", False, "LIQUIDITY_UNACCEPTABLE"),
        ("regime_clear", False, "REGIME_UNCLEAR"),
        ("deterministic_setup", False, "NO_DETERMINISTIC_SETUP"),
        ("complete_trade_plan", False, "INCOMPLETE_TRADE_PLAN"),
        ("risk_budget_available", False, "RISK_BUDGET_UNAVAILABLE"),
        ("cooldown_clear", False, "COOLDOWN_ACTIVE"),
        ("event_blackout", True, "MACRO_EVENT_BLACKOUT"),
    ],
)
def test_professional_habit_gate_holds_when_check_fails(
    field: str,
    value: object,
    reason: str,
) -> None:
    result = ProfessionalChecklist().evaluate(replace(valid_inputs(), **{field: value}))

    assert result.action is ChecklistAction.HOLD
    assert result.reason_codes == (reason,)


def test_stale_uncited_conflicting_or_injected_context_holds() -> None:
    checklist = ProfessionalChecklist(max_context_age=timedelta(minutes=30))
    stale = replace(fresh_context(), fetched_at=NOW - timedelta(hours=1))
    assert checklist.evaluate(replace(valid_inputs(), context=stale)).reason_codes == (
        "STALE_CONTEXT",
    )

    uncited = ContextSnapshot.build(
        fetched_at=NOW,
        sources=(),
        items=(
            ContextItem(
                summary="Unverified claim",
                driver="geopolitics",
                direction="bullish",
                severity="high",
                published_at=NOW,
                source_indexes=(),
                contradictory=False,
            ),
        ),
    )
    assert checklist.evaluate(replace(valid_inputs(), context=uncited)).reason_codes == (
        "UNCITED_CONTEXT",
    )

    conflicting = replace(
        fresh_context(),
        items=(replace(fresh_context().items[0], contradictory=True),),
    )
    assert checklist.evaluate(replace(valid_inputs(), context=conflicting)).reason_codes == (
        "CONTRADICTORY_CONTEXT",
    )

    injected = replace(fresh_context(), prompt_injection_suspected=True)
    assert checklist.evaluate(replace(valid_inputs(), context=injected)).reason_codes == (
        "UNTRUSTED_CONTEXT_INSTRUCTIONS",
    )
