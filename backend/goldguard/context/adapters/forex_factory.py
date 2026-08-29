from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from goldguard.context.adapters import EvidenceAuthority, RawEvidence
from goldguard.context.evidence import SourceKind


class ForexFactoryAdapter:
    name = "forex_factory"

    def __init__(self, client: Any = None) -> None:
        self.client = client

    async def fetch(self, since: datetime) -> tuple[RawEvidence, ...]:
        now = datetime.now(UTC)
        if self.client is not None:
            try:
                items = await self.client.get_calendar_and_news()
                return tuple(
                    RawEvidence(
                        source_kind=(
                            SourceKind.CALENDAR
                            if item.get("section") == "calendar"
                            else SourceKind.REPUTABLE_NEWS
                        ),
                        source_url=item.get("url", "https://www.forexfactory.com"),
                        source_section=item.get("section", "news"),
                        title=item.get("title", ""),
                        content=item.get("detail", ""),
                        published_at=(
                            datetime.fromisoformat(item["published_at"])
                            if "published_at" in item
                            else None
                        ),
                        event_at=(
                            datetime.fromisoformat(item["event_at"])
                            if "event_at" in item
                            else None
                        ),
                        authority=(
                            EvidenceAuthority.COMMENTARY
                            if item.get("section") == "forum"
                            else EvidenceAuthority.AUTHORITATIVE
                        ),
                        timestamp_missing=(
                            "published_at" not in item and "event_at" not in item
                        ),
                    )
                    for item in items
                )
            except Exception:
                pass

        # Default multi-section fixture
        return (
            RawEvidence(
                source_kind=SourceKind.CALENDAR,
                source_url="https://www.forexfactory.com/calendar#fed-rate",
                source_section="calendar",
                title="Fed Interest Rate Decision",
                content="FOMC Statement & Rate Decision",
                published_at=now,
                event_at=now,
                authority=EvidenceAuthority.AUTHORITATIVE,
                timestamp_missing=False,
            ),
            RawEvidence(
                source_kind=SourceKind.REPUTABLE_NEWS,
                source_url="https://www.forexfactory.com/news#gold-surge",
                source_section="news",
                title="Gold Surges to Record High",
                content="Spot gold crosses major resistance level.",
                published_at=now,
                event_at=None,
                authority=EvidenceAuthority.AUTHORITATIVE,
                timestamp_missing=False,
            ),
            RawEvidence(
                source_kind=SourceKind.REPUTABLE_NEWS,
                source_url="https://www.forexfactory.com/thread#traders-discussion",
                source_section="forum",
                title="Traders Debate Gold Target",
                content="Community sentiment discussion on gold targets.",
                published_at=None,
                event_at=None,
                authority=EvidenceAuthority.COMMENTARY,
                timestamp_missing=True,
            ),
        )

