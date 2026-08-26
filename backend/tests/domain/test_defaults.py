from decimal import Decimal

import pytest
from goldguard.domain.defaults import SAFE_DEFAULT_V1, StrategySettings
from pydantic import ValidationError


def test_safe_default_v1_matches_approved_risk_profile() -> None:
    assert SAFE_DEFAULT_V1.version == "safe-default-v1"
    assert SAFE_DEFAULT_V1.paper_starting_balance == Decimal("100")
    assert SAFE_DEFAULT_V1.risk_per_trade == Decimal("0.005")
    assert SAFE_DEFAULT_V1.daily_loss_halt == Decimal("0.03")
    assert SAFE_DEFAULT_V1.emergency_drawdown_halt == Decimal("0.05")
    assert SAFE_DEFAULT_V1.stop_atr_multiple == Decimal("1.5")
    assert SAFE_DEFAULT_V1.reward_r_multiple == Decimal("2")
    assert SAFE_DEFAULT_V1.maximum_positions == 1


def test_safe_default_is_frozen() -> None:
    with pytest.raises(ValidationError, match="frozen"):
        SAFE_DEFAULT_V1.risk_per_trade = Decimal("0.01")


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("risk_per_trade", "0.02"),
        ("daily_loss_halt", "0.04"),
        ("emergency_drawdown_halt", "0.06"),
        ("cooldown_minutes", 10),
        ("maximum_positions", 2),
    ],
)
def test_settings_reject_values_outside_hard_safety_ranges(field: str, value: object) -> None:
    with pytest.raises(ValidationError):
        StrategySettings.model_validate({**SAFE_DEFAULT_V1.model_dump(), field: value})


def test_emergency_drawdown_must_exceed_daily_halt() -> None:
    with pytest.raises(ValidationError, match="greater than daily"):
        StrategySettings.model_validate(
            {
                **SAFE_DEFAULT_V1.model_dump(),
                "daily_loss_halt": "0.03",
                "emergency_drawdown_halt": "0.03",
            }
        )
