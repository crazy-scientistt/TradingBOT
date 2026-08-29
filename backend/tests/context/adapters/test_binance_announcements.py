from __future__ import annotations

from datetime import UTC, datetime

import pytest
from goldguard.context.adapters import EvidenceAuthority
from goldguard.context.adapters.binance_announcements import BinanceAnnouncementsAdapter
from goldguard.context.evidence import SourceKind


@pytest.mark.asyncio
async def test_binance_announcements_adapter_fetch() -> None:
    adapter = BinanceAnnouncementsAdapter()
    since = datetime(2026, 8, 28, 0, 0, 0, tzinfo=UTC)
    results = await adapter.fetch(since)

    assert len(results) >= 1
    item = results[0]
    assert item.source_kind == SourceKind.EXCHANGE
    assert item.authority == EvidenceAuthority.AUTHORITATIVE
    assert "binance.com" in item.source_url

