from __future__ import annotations

from datetime import datetime
from typing import Any

from goldguard.context.adapters import EvidenceAuthority, RawEvidence
from goldguard.context.evidence import SourceKind


class OfficialReleasesAdapter:
    name = "official_releases"

    def __init__(self, client: Any = None) -> None:
        self.client = client

    async def fetch(self, since: datetime) -> tuple[RawEvidence, ...]:
        if self.client is None:
            return ()
        try:
            items = await self.client.get_releases()
        except Exception:
            return ()
        rows: list[RawEvidence] = []
        for item in items:
            published = (
                datetime.fromisoformat(item["published_at"])
                if item.get("published_at")
                else None
            )
            event_at = (
                datetime.fromisoformat(item["event_at"]) if item.get("event_at") else None
            )
            rows.append(
                RawEvidence(
                    source_kind=SourceKind.OFFICIAL,
                    source_url=item.get("url", "https://www.federalreserve.gov"),
                    source_section=item.get("section", "release"),
                    title=item.get("title", ""),
                    content=item.get("body", item.get("detail", "")),
                    published_at=published,
                    event_at=event_at,
                    authority=EvidenceAuthority.AUTHORITATIVE,
                    timestamp_missing=published is None and event_at is None,
                )
            )
        return tuple(rows)
