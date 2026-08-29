from __future__ import annotations

import pytest
from goldguard.domain.profile import default_autonomous_profile
from goldguard.live.reconciliation import ReconciliationService


class ExchangeMock:
    def __init__(self) -> None:
        self.has_unknown_position = False
        self.missing_stop = False
        self.close_calls: list[str] = []


@pytest.mark.asyncio
async def test_unknown_external_position_blocks_without_closing() -> None:
    exchange = ExchangeMock()
    exchange.has_unknown_position = True
    service = ReconciliationService(exchange_client=exchange)

    profile = default_autonomous_profile()
    report = await service.reconcile(profile, "startup")
    assert "UNKNOWN_EXTERNAL_POSITION" in report.blockers
    assert exchange.close_calls == []


@pytest.mark.asyncio
async def test_missing_exchange_fails_closed() -> None:
    service = ReconciliationService()
    report = await service.reconcile(default_autonomous_profile(), "startup")
    assert report.ready is False
    assert "EXCHANGE_UNAVAILABLE" in report.blockers
