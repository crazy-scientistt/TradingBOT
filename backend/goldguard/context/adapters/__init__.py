from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import Protocol

from goldguard.context.evidence import SourceKind


class EvidenceAuthority(StrEnum):
    AUTHORITATIVE = "authoritative"
    COMMENTARY = "commentary"
    UNVERIFIED = "unverified"


@dataclass(frozen=True, slots=True)
class RawEvidence:
    source_kind: SourceKind
    source_url: str
    source_section: str  # "calendar", "news", "forum", "announcements", "release"
    title: str
    content: str
    published_at: datetime | None
    event_at: datetime | None
    authority: EvidenceAuthority
    timestamp_missing: bool = False


class EvidenceAdapter(Protocol):
    name: str

    async def fetch(self, since: datetime) -> tuple[RawEvidence, ...]: ...

