from __future__ import annotations

from datetime import datetime
from typing import Any

from goldguard.context.adapters import EvidenceAuthority, RawEvidence
from goldguard.context.evidence import SourceKind


class ForexFactoryAdapter:
    name = "forex_factory"

    def __init__(self, client: Any = None) -> None:
        self.client = client

    async def fetch(self, since: datetime) -> tuple[RawEvidence, ...]:
        if self.client is None:
            return ()
        try:
            items = await self.client.get_calendar_and_news()
        except Exception:
            return ()
        rows: list[RawEvidence] = []
        for item in items:
            section = item.get("section", "news")
            published = (
                datetime.fromisoformat(item["published_at"])
                if item.get("published_at")
                else None
            )
            event_at = (
                datetime.fromisoformat(item["event_at"]) if item.get("event_at") else None
            )
            source_kind = (
                SourceKind.CALENDAR
                if section == "calendar"
                else SourceKind.REPUTABLE_NEWS
            )
            authority = (
                EvidenceAuthority.COMMENTARY
                if section == "forum"
                else EvidenceAuthority.AUTHORITATIVE
            )
            rows.append(
                RawEvidence(
                    source_kind=source_kind,
                    source_url=item.get("url", "https://www.forexfactory.com"),
                    source_section=section,
                    title=item.get("title", ""),
                    content=item.get("detail", ""),
                    published_at=published,
                    event_at=event_at,
                    authority=authority,
                    timestamp_missing=published is None and event_at is None,
                )
            )
        return tuple(rows)
