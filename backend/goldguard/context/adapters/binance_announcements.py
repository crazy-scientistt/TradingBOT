from __future__ import annotations

from datetime import datetime
from typing import Any

from goldguard.context.adapters import EvidenceAuthority, RawEvidence
from goldguard.context.evidence import SourceKind


class BinanceAnnouncementsAdapter:
    name = "binance_announcements"

    def __init__(self, client: Any = None) -> None:
        self.client = client

    async def fetch(self, since: datetime) -> tuple[RawEvidence, ...]:
        if self.client is None:
            return ()
        try:
            items = await self.client.get_announcements()
        except Exception:
            return ()
        rows: list[RawEvidence] = []
        for item in items:
            published = None
            if item.get("published_at"):
                published = datetime.fromisoformat(item["published_at"])
            rows.append(
                RawEvidence(
                    source_kind=SourceKind.EXCHANGE,
                    source_url=item.get(
                        "url", "https://www.binance.com/en/support/announcement"
                    ),
                    source_section="announcements",
                    title=item.get("title", ""),
                    content=item.get("body", ""),
                    published_at=published,
                    event_at=None,
                    authority=EvidenceAuthority.AUTHORITATIVE,
                    timestamp_missing="published_at" not in item or not item.get("published_at"),
                )
            )
        return tuple(rows)
