from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from goldguard.context.adapters import EvidenceAuthority, RawEvidence
from goldguard.context.evidence import SourceKind


class OfficialReleasesAdapter:
    name = "official_releases"

    def __init__(self, client: Any = None) -> None:
        self.client = client

    async def fetch(self, since: datetime) -> tuple[RawEvidence, ...]:
        now = datetime.now(UTC)
        return (
            RawEvidence(
                source_kind=SourceKind.OFFICIAL,
                source_url="https://www.federalreserve.gov/newsevents/pressreleases/monetary20260828a.htm",
                source_section="release",
                title="Federal Reserve Press Release",
                content="Federal Reserve issues FOMC statement on economic outlook.",
                published_at=now,
                event_at=None,
                authority=EvidenceAuthority.AUTHORITATIVE,
                timestamp_missing=False,
            ),
        )

