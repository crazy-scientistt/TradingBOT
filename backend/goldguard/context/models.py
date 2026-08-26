import hashlib
import json
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from typing import Literal
from urllib.parse import urlparse

PRIMARY_DOMAINS = (
    "federalreserve.gov",
    "bls.gov",
    "bea.gov",
    "treasury.gov",
    "cftc.gov",
    "paxos.com",
    "binance.com",
    "developers.binance.com",
    "gold.org",
)


def source_tier(url: str) -> int:
    hostname = (urlparse(url).hostname or "").lower()
    if any(hostname == domain or hostname.endswith(f".{domain}") for domain in PRIMARY_DOMAINS):
        return 1
    if hostname.endswith(("reuters.com", "apnews.com", "ft.com", "wsj.com")):
        return 2
    return 3


def require_utc(value: datetime, label: str) -> datetime:
    if value.tzinfo is None or value.utcoffset() != UTC.utcoffset(value):
        raise ValueError(f"{label} must be timezone-aware UTC")
    return value.astimezone(UTC)


@dataclass(frozen=True)
class ContextSource:
    url: str
    title: str
    published_at: datetime | None
    tier: int = field(init=False)

    def __post_init__(self) -> None:
        parsed = urlparse(self.url)
        if parsed.scheme != "https" or not parsed.hostname:
            raise ValueError("context source must use an absolute HTTPS URL")
        if self.published_at is not None:
            object.__setattr__(self, "published_at", require_utc(self.published_at, "published_at"))
        object.__setattr__(self, "tier", source_tier(self.url))


@dataclass(frozen=True)
class ContextItem:
    summary: str
    driver: str
    direction: Literal["bullish", "bearish", "neutral", "mixed"]
    severity: Literal["low", "medium", "high", "critical"]
    published_at: datetime | None
    source_indexes: tuple[int, ...]
    contradictory: bool

    def __post_init__(self) -> None:
        if not self.summary.strip() or len(self.summary) > 500:
            raise ValueError("context summary must contain 1-500 characters")
        if self.published_at is not None:
            object.__setattr__(self, "published_at", require_utc(self.published_at, "published_at"))


@dataclass(frozen=True)
class ContextSnapshot:
    fetched_at: datetime
    sources: tuple[ContextSource, ...]
    items: tuple[ContextItem, ...]
    content_hash: str
    prompt_injection_suspected: bool = False

    def __post_init__(self) -> None:
        object.__setattr__(self, "fetched_at", require_utc(self.fetched_at, "fetched_at"))

    @classmethod
    def build(
        cls,
        *,
        fetched_at: datetime,
        sources: tuple[ContextSource, ...],
        items: tuple[ContextItem, ...],
        prompt_injection_suspected: bool = False,
    ) -> "ContextSnapshot":
        canonical = json.dumps(
            {
                "fetched_at": fetched_at.isoformat(),
                "sources": [asdict(source) for source in sources],
                "items": [asdict(item) for item in items],
                "prompt_injection_suspected": prompt_injection_suspected,
            },
            default=str,
            sort_keys=True,
            separators=(",", ":"),
        )
        return cls(
            fetched_at=fetched_at,
            sources=sources,
            items=items,
            content_hash=hashlib.sha256(canonical.encode()).hexdigest(),
            prompt_injection_suspected=prompt_injection_suspected,
        )
