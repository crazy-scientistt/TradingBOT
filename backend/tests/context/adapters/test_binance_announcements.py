from __future__ import annotations

from datetime import UTC, datetime

import pytest
from goldguard.context.adapters import EvidenceAuthority
from goldguard.context.adapters.binance_announcements import BinanceAnnouncementsAdapter
from goldguard.context.evidence import SourceKind


class FixtureAnnouncements:
    async def get_announcements(self) -> list[dict[str, str]]:
        return [
            {
                "url": "https://www.binance.com/en/support/announcement/paxg-maintenance",
                "title": "PAXG/USDT Maintenance Notice",
                "body": "Scheduled wallet maintenance for PAXG completed.",
                "published_at": "2026-08-28T00:00:00+00:00",
            }
        ]


@pytest.mark.asyncio
async def test_binance_announcements_adapter_fetch() -> None:
    adapter = BinanceAnnouncementsAdapter(client=FixtureAnnouncements())
    since = datetime(2026, 8, 28, 0, 0, 0, tzinfo=UTC)
    results = await adapter.fetch(since)

    assert len(results) >= 1
    item = results[0]
    assert item.source_kind == SourceKind.EXCHANGE
    assert item.authority == EvidenceAuthority.AUTHORITATIVE
    assert "binance.com" in item.source_url


@pytest.mark.asyncio
async def test_binance_announcements_without_client_returns_empty() -> None:
    adapter = BinanceAnnouncementsAdapter()
    results = await adapter.fetch(datetime(2026, 8, 28, tzinfo=UTC))
    assert results == ()
