"""Execution adapters for paper and explicitly armed live trading."""

from goldguard.broker.base import Broker, ClosedPaperTrade, PaperFill, PaperPosition
from goldguard.broker.paper import PaperBroker, PaperOrderRejected
from goldguard.broker.safety_guard import SafetyGuardError, check_safe_url

__all__ = [
    "Broker",
    "ClosedPaperTrade",
    "PaperBroker",
    "PaperFill",
    "PaperOrderRejected",
    "PaperPosition",
    "SafetyGuardError",
    "check_safe_url",
]

