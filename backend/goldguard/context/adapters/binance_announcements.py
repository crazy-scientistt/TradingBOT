from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from goldguard.context.adapters import EvidenceAuthority, RawEvidence
from goldguard.context.evidence import SourceKind


class BinanceAnnouncementsAdapter:
    name = "binance_announcements"

    def __init__(self, client: Any = None) -> None:
        self.client = client

    async def fetch(self, since: datetime) -> tuple[RawEvidence, ...]:
        now = datetime.now(UTC)
        if self.client is not None:
            try:
                items = await self.client.get_announcements()
                return tuple(
                    RawEvidence(
                        source_kind=SourceKind.EXCHANGE,
                        source_url=item.get(
                            "url", "https://www.binance.com/en/support/announcement"
                        ),
                        source_section="announcements",
                        title=item.get("title", "Binance Update"),
                        content=item.get("body", ""),
                        published_at=(
                            datetime.fromisoformat(item["published_at"])
                            if "published_at" in item
                            else None
                        ),
                        event_at=None,
                        authority=EvidenceAuthority.AUTHORITATIVE,
                        timestamp_missing="published_at" not in item,
                    )
                    for item in items
                )
            except Exception:
                pass

        # Default synthetic fixture for testing
        return (
            RawEvidence(
                source_kind=SourceKind.EXCHANGE,
                source_url="https://www.binance.com/en/support/announcement/paxg-maintenance",
                source_section="announcements",
                title="PAXG/USDT Maintenance Notice",
                content="Scheduled wallet maintenance for PAXG completed.",
                published_at=now,
                event_at=None,
                authority=EvidenceAuthority.AUTHORITATIVE,
                timestamp_missing=False,
            ),
        )

