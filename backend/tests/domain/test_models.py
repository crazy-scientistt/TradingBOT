from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from goldguard.domain.enums import AiDecision, CandidateAction
from goldguard.domain.models import Candle, TradePlan, ai_decision_is_compatible
from pydantic import ValidationError


def test_candle_requires_utc_and_valid_ohlc() -> None:
    opened = datetime(2026, 8, 26, tzinfo=UTC)
    candle = Candle(
        symbol="PAXGUSDT",
        timeframe="15m",
        open_time=opened,
        close_time=opened + timedelta(minutes=15),
        open=Decimal("2500.10"),
        high=Decimal("2508.40"),
        low=Decimal("2498.20"),
        close=Decimal("2506.75"),
        volume=Decimal("12.5"),
        closed=True,
    )

    assert candle.close == Decimal("2506.75")
    assert isinstance(candle.close, Decimal)

    with pytest.raises(ValidationError, match="timezone-aware UTC"):
        Candle.model_validate({**candle.model_dump(), "open_time": opened.replace(tzinfo=None)})

    with pytest.raises(ValidationError, match="high must cover"):
        Candle.model_validate({**candle.model_dump(), "high": Decimal("2499")})


def test_money_fields_reject_binary_floats() -> None:
    with pytest.raises(ValidationError, match="decimal string or Decimal"):
        TradePlan(
            entry=2500.0,
            stop=Decimal("2487.50"),
            target=Decimal("2525"),
            quantity=Decimal("0.02"),
            risk_amount=Decimal("0.25"),
            expected_fees=Decimal("0.10"),
        )


def test_trade_plan_is_long_only_and_rejects_stop_widening() -> None:
    plan = TradePlan(
        entry=Decimal("2500"),
        stop=Decimal("2487.50"),
        target=Decimal("2525"),
        quantity=Decimal("0.02"),
        risk_amount=Decimal("0.25"),
        expected_fees=Decimal("0.10"),
    )

    tightened = plan.with_stop(Decimal("2492"))
    assert tightened.stop == Decimal("2492")

    with pytest.raises(ValueError, match="stop widening"):
        plan.with_stop(Decimal("2480"))

    with pytest.raises(ValidationError, match="stop must be below entry"):
        TradePlan.model_validate({**plan.model_dump(), "stop": Decimal("2500")})

    with pytest.raises(ValidationError, match="target must be above entry"):
        TradePlan.model_validate({**plan.model_dump(), "target": Decimal("2499")})


@pytest.mark.parametrize(
    ("candidate", "decision", "expected"),
    [
        (CandidateAction.ENTRY_CANDIDATE, AiDecision.APPROVE_ENTRY, True),
        (CandidateAction.ENTRY_CANDIDATE, AiDecision.REJECT_ENTRY, True),
        (CandidateAction.ENTRY_CANDIDATE, AiDecision.EXIT, False),
        (CandidateAction.EXIT_CANDIDATE, AiDecision.EXIT, True),
        (CandidateAction.EXIT_CANDIDATE, AiDecision.APPROVE_ENTRY, False),
        (CandidateAction.NO_ACTION, AiDecision.HOLD, True),
        (CandidateAction.NO_ACTION, AiDecision.APPROVE_ENTRY, False),
    ],
)
def test_ai_decisions_are_compatible_with_deterministic_candidates(
    candidate: CandidateAction,
    decision: AiDecision,
    expected: bool,
) -> None:
    assert ai_decision_is_compatible(candidate, decision) is expected
