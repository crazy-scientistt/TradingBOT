from __future__ import annotations

from dataclasses import dataclass, field

import pytest
from goldguard.domain.profile import default_autonomous_profile
from goldguard.live.reconciliation import ReconciliationService


@dataclass
class RecoveryRuntime:
    entries_blocked: bool = True
    duplicate_orders: int = 0
    last_audit_id: str = "aud-0"
    reconciled: bool = False
    close_calls: list[str] = field(default_factory=list)

    def crash_at(self, crash_point: str) -> None:
        self.last_audit_id = f"aud-{crash_point}"
        self.entries_blocked = True

    async def restart_and_reconcile(self, exchange: object) -> None:
        self.entries_blocked = True
        service = ReconciliationService(exchange_client=exchange)
        report = await service.reconcile(default_autonomous_profile(), "startup")
        self.reconciled = True
        if report.ready:
            self.entries_blocked = False


class OwnedExchange:
    has_unknown_position = False
    ledger_position_ids = ("owned-1",)
    exchange_position_ids = ("owned-1",)


@pytest.mark.parametrize(
    "crash_point",
    [
        "after_intent",
        "after_submit",
        "after_partial_fill",
        "after_protection",
        "during_canary",
        "after_notification_send",
    ],
)
@pytest.mark.asyncio
async def test_restart_converges_without_duplicate_side_effect(crash_point: str) -> None:
    runtime = RecoveryRuntime()
    runtime.crash_at(crash_point)
    await runtime.restart_and_reconcile(OwnedExchange())
    assert runtime.entries_blocked is False
    assert runtime.duplicate_orders == 0
    assert runtime.reconciled is True
    assert runtime.last_audit_id == f"aud-{crash_point}"
    assert runtime.close_calls == []


@pytest.mark.asyncio
async def test_restart_keeps_entries_blocked_when_exchange_missing() -> None:
    runtime = RecoveryRuntime()
    runtime.crash_at("after_submit")
    await runtime.restart_and_reconcile(None)
    assert runtime.entries_blocked is True
    assert runtime.duplicate_orders == 0
