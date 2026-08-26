"""Canonical trading domain types."""

from goldguard.domain.enums import (
    AiDecision,
    BotMode,
    BotState,
    CandidateAction,
    ChecklistAction,
    ExitReason,
    OrderSide,
)
from goldguard.domain.models import (
    Candle,
    MoneyRange,
    Quote,
    RiskLimitPreset,
    TradePlan,
    ai_decision_is_compatible,
)

__all__ = [
    "AiDecision",
    "BotMode",
    "BotState",
    "CandidateAction",
    "Candle",
    "ChecklistAction",
    "ExitReason",
    "MoneyRange",
    "OrderSide",
    "Quote",
    "RiskLimitPreset",
    "TradePlan",
    "ai_decision_is_compatible",
]
