from __future__ import annotations

from datetime import UTC, datetime

import pytest
from goldguard.context.adapters import EvidenceAuthority
from goldguard.context.adapters.forex_factory import ForexFactoryAdapter


class FixtureForexFactory:
    async def get_calendar_and_news(self) -> list[dict[str, str]]:
        return [
            {
                "section": "calendar",
                "url": "https://www.forexfactory.com/calendar#fed-rate",
                "title": "Fed Interest Rate Decision",
                "detail": "FOMC Statement & Rate Decision",
                "published_at": "2026-08-28T00:00:00+00:00",
                "event_at": "2026-08-28T18:00:00+00:00",
            },
            {
                "section": "news",
                "url": "https://www.forexfactory.com/news#gold-surge",
                "title": "Gold Surges to Record High",
                "detail": "Spot gold crosses major resistance level.",
                "published_at": "2026-08-28T00:00:00+00:00",
            },
            {
                "section": "forum",
                "url": "https://www.forexfactory.com/thread#traders-discussion",
                "title": "Traders Debate Gold Target",
                "detail": "Community sentiment discussion on gold targets.",
            },
        ]


@pytest.mark.asyncio
async def test_forex_factory_forum_is_non_authoritative() -> None:
    adapter = ForexFactoryAdapter(client=FixtureForexFactory())
    since = datetime(2026, 8, 28, 0, 0, 0, tzinfo=UTC)
    rows = await adapter.fetch(since)

    forum = next(row for row in rows if row.source_section == "forum")
    assert forum.authority == EvidenceAuthority.COMMENTARY
    assert forum.timestamp_missing is True

    calendar = next(row for row in rows if row.source_section == "calendar")
    assert calendar.authority == EvidenceAuthority.AUTHORITATIVE


@pytest.mark.asyncio
async def test_forex_factory_without_client_returns_empty() -> None:
    adapter = ForexFactoryAdapter()
    rows = await adapter.fetch(datetime(2026, 8, 28, tzinfo=UTC))
    assert rows == ()
