from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from goldguard.memory.outcomes import (
    DecisionQuality,
    OutcomeAttributor,
    OutcomeCategory,
)


@dataclass
class TradeMock:
    net_pnl: Decimal
    compliant: bool
    positive_expected_edge: bool


def test_rule_followed_loss_is_normal_variance() -> None:
    attributor = OutcomeAttributor()
    mock_trade = TradeMock(net_pnl=Decimal("-1.25"), compliant=True, positive_expected_edge=True)
    res = attributor.attribute(mock_trade)
    assert res.primary_category == OutcomeCategory.NORMAL_VARIANCE
    assert res.decision_quality == DecisionQuality.SOUND


def test_winning_rule_violation_is_invalid() -> None:
    attributor = OutcomeAttributor()
    mock_trade = TradeMock(net_pnl=Decimal("5.00"), compliant=False, positive_expected_edge=True)
    res = attributor.attribute(mock_trade)
    assert res.decision_quality == DecisionQuality.INVALID

