from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from enum import StrEnum
from typing import Any


class OutcomeCategory(StrEnum):
    HYPOTHESIS = "hypothesis"
    TIMING = "timing"
    REGIME = "regime"
    EVIDENCE = "evidence"
    SIZING = "sizing"
    EXECUTION = "execution"
    PROTECTION = "protection"
    SYSTEM = "system"
    NORMAL_VARIANCE = "normal_variance"


class DecisionQuality(StrEnum):
    SOUND = "sound"
    SUBOPTIMAL = "suboptimal"
    INVALID = "invalid"


@dataclass(frozen=True, slots=True)
class OutcomeAttribution:
    primary_category: OutcomeCategory
    decision_quality: DecisionQuality
    net_pnl: Decimal
    explanation: str


class OutcomeAttributor:
    def attribute(self, trade_record: Any) -> OutcomeAttribution:
        net_pnl = getattr(trade_record, "net_pnl", Decimal("0"))
        compliant = getattr(trade_record, "compliant", True)
        positive_edge = getattr(trade_record, "positive_expected_edge", True)

        if not compliant:
            return OutcomeAttribution(
                primary_category=OutcomeCategory.EXECUTION,
                decision_quality=DecisionQuality.INVALID,
                net_pnl=net_pnl,
                explanation="trade violated execution rules or risk ceilings",
            )

        if net_pnl < 0 and positive_edge:
            return OutcomeAttribution(
                primary_category=OutcomeCategory.NORMAL_VARIANCE,
                decision_quality=DecisionQuality.SOUND,
                net_pnl=net_pnl,
                explanation=(
                    "rule-compliant loss with positive expected edge is normal statistical variance"
                ),
            )

        return OutcomeAttribution(
            primary_category=OutcomeCategory.HYPOTHESIS,
            decision_quality=DecisionQuality.SOUND,
            net_pnl=net_pnl,
            explanation="trade executed soundly according to strategy specification",
        )

