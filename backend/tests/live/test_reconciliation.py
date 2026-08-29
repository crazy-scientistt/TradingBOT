from __future__ import annotations

import pytest
from goldguard.domain.profile import default_autonomous_profile
from goldguard.live.reconciliation import ReconciliationService


class ExchangeMock:
    def __init__(self) -> None:
        self.has_unknown_position = False
        self.missing_stop = False
        self.close_calls: list[str] = []
        self.ledger_position_ids: tuple[str, ...] = ()
        self.exchange_position_ids: tuple[str, ...] = ()


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
async def test_snapshot_unknown_position_is_not_adopted() -> None:
    exchange = ExchangeMock()
    exchange.ledger_position_ids = ("owned-1",)
    exchange.exchange_position_ids = ("owned-1", "external-9")
    service = ReconciliationService(exchange_client=exchange)
    report = await service.reconcile(default_autonomous_profile(), "startup")
    assert "UNKNOWN_EXTERNAL_POSITION" in report.blockers
    assert report.ready is False
    assert exchange.close_calls == []


@pytest.mark.asyncio
async def test_missing_exchange_is_not_ready() -> None:
    service = ReconciliationService()
    report = await service.reconcile(default_autonomous_profile())
    assert report.ready is False
    assert "EXCHANGE_UNAVAILABLE" in report.blockers
