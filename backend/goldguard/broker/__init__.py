"""Execution adapters for paper and explicitly armed live trading."""

from goldguard.broker.base import Broker, ClosedPaperTrade, PaperFill, PaperPosition
from goldguard.broker.paper import PaperBroker, PaperOrderRejected

__all__ = [
    "Broker",
    "ClosedPaperTrade",
    "PaperBroker",
    "PaperFill",
    "PaperOrderRejected",
    "PaperPosition",
]
