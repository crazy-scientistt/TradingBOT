from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from goldguard.domain.profile import AutonomousProfile


@dataclass(frozen=True, slots=True)
class ReconciliationReport:
    ready: bool
    blockers: tuple[str, ...] = field(default_factory=tuple)
    repaired: tuple[str, ...] = field(default_factory=tuple)


class ReconciliationService:
    def __init__(self, exchange_client: Any = None, arming_service: Any = None) -> None:
        self.exchange = exchange_client
        self.arming = arming_service

    async def reconcile(
        self, profile: AutonomousProfile, reason: str = "startup"
    ) -> ReconciliationReport:
        if self.exchange is None:
            return ReconciliationReport(
                ready=False,
                blockers=("EXCHANGE_UNAVAILABLE",),
            )

        blockers: list[str] = []
        repaired: list[str] = []

        if getattr(self.exchange, "has_unknown_position", False):
            blockers.append("UNKNOWN_EXTERNAL_POSITION")

        if getattr(self.exchange, "missing_stop", False):
            repaired.append("MISSING_STOP:position-1")

        if getattr(self.exchange, "has_unknown_order", False):
            blockers.append("UNKNOWN_EXTERNAL_ORDER")

        return ReconciliationReport(
            ready=len(blockers) == 0,
            blockers=tuple(blockers),
            repaired=tuple(repaired),
        )
