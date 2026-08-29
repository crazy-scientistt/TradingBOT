from __future__ import annotations

from datetime import UTC, datetime

import pytest
from goldguard.context.adapters import EvidenceAuthority
from goldguard.context.adapters.official_releases import OfficialReleasesAdapter
from goldguard.context.evidence import SourceKind


class FixtureReleases:
    async def get_releases(self) -> list[dict[str, str]]:
        return [
            {
                "url": "https://www.federalreserve.gov/newsevents/pressreleases/monetary20260828a.htm",
                "title": "Federal Reserve Press Release",
                "body": "Federal Reserve issues FOMC statement on economic outlook.",
                "published_at": "2026-08-28T00:00:00+00:00",
                "section": "release",
            }
        ]


@pytest.mark.asyncio
async def test_official_releases_adapter_fetch() -> None:
    adapter = OfficialReleasesAdapter(client=FixtureReleases())
    since = datetime(2026, 8, 28, 0, 0, 0, tzinfo=UTC)
    results = await adapter.fetch(since)

    assert len(results) >= 1
    release = results[0]
    assert release.source_kind == SourceKind.OFFICIAL
    assert release.authority == EvidenceAuthority.AUTHORITATIVE
    assert "federalreserve.gov" in release.source_url


@pytest.mark.asyncio
async def test_official_releases_without_client_returns_empty() -> None:
    adapter = OfficialReleasesAdapter()
    results = await adapter.fetch(datetime(2026, 8, 28, tzinfo=UTC))
    assert results == ()
