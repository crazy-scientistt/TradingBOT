from __future__ import annotations

from goldguard.domain.profile import AutonomousProfile
from goldguard.live.reconciliation import ReconciliationReport, ReconciliationService


class ReconciliationSupervisor:
    def __init__(self, service: ReconciliationService) -> None:
        self.service = service

    async def startup_reconcile(self, profile: AutonomousProfile) -> ReconciliationReport:
        return await self.service.reconcile(profile, reason="startup")

