from __future__ import annotations

from collections.abc import Iterable
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
        _ = profile, reason
        if self.exchange is None:
            return ReconciliationReport(
                ready=False,
                blockers=("EXCHANGE_UNAVAILABLE",),
            )

        blockers: list[str] = []
        repaired: list[str] = []

        if getattr(self.exchange, "has_unknown_position", False):
            blockers.append("UNKNOWN_EXTERNAL_POSITION")
        if getattr(self.exchange, "has_unknown_order", False):
            blockers.append("UNKNOWN_EXTERNAL_ORDER")
        if getattr(self.exchange, "missing_stop", False):
            repaired.append("MISSING_STOP:position-1")

        ledger_ids = _id_set(getattr(self.exchange, "ledger_position_ids", ()))
        exchange_ids = _id_set(getattr(self.exchange, "exchange_position_ids", ()))
        if ledger_ids or exchange_ids:
            unknown = exchange_ids - ledger_ids
            if unknown and "UNKNOWN_EXTERNAL_POSITION" not in blockers:
                blockers.append("UNKNOWN_EXTERNAL_POSITION")
            missing = ledger_ids - exchange_ids
            if missing:
                blockers.append("LEDGER_POSITION_MISSING_ON_EXCHANGE")

        missing_stops = _id_set(getattr(self.exchange, "positions_missing_stops", ()))
        for position_id in missing_stops:
            if position_id in ledger_ids:
                repaired.append(f"MISSING_STOP:{position_id}")

        return ReconciliationReport(
            ready=len(blockers) == 0,
            blockers=tuple(blockers),
            repaired=tuple(repaired),
        )


def _id_set(values: Iterable[object]) -> set[str]:
    return {str(item) for item in values}
