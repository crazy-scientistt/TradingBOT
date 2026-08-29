from __future__ import annotations

from datetime import UTC, datetime

import pytest
from goldguard.context.adapters import EvidenceAuthority
from goldguard.context.adapters.official_releases import OfficialReleasesAdapter
from goldguard.context.evidence import SourceKind


@pytest.mark.asyncio
async def test_official_releases_adapter_fetch() -> None:
    adapter = OfficialReleasesAdapter()
    since = datetime(2026, 8, 28, 0, 0, 0, tzinfo=UTC)
    results = await adapter.fetch(since)

    assert len(results) >= 1
    release = results[0]
    assert release.source_kind == SourceKind.OFFICIAL
    assert release.authority == EvidenceAuthority.AUTHORITATIVE
    assert "federalreserve.gov" in release.source_url

