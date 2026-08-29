from __future__ import annotations

from datetime import UTC, datetime

import pytest
from goldguard.context.adapters import EvidenceAuthority
from goldguard.context.adapters.forex_factory import ForexFactoryAdapter


@pytest.mark.asyncio
async def test_forex_factory_forum_is_non_authoritative() -> None:
    adapter = ForexFactoryAdapter()
    since = datetime(2026, 8, 28, 0, 0, 0, tzinfo=UTC)
    rows = await adapter.fetch(since)

    forum = next(row for row in rows if row.source_section == "forum")
    assert forum.authority == EvidenceAuthority.COMMENTARY
    assert forum.timestamp_missing is True

    calendar = next(row for row in rows if row.source_section == "calendar")
    assert calendar.authority == EvidenceAuthority.AUTHORITATIVE

