from datetime import UTC, datetime

from goldguard.context.models import ContextItem, ContextSnapshot
from goldguard.context.sources import (
    SearchProvider,
    deduplicate_and_filter_sources,
    normalize_url,
)
from goldguard.storage.repositories import QuotaRepository


def detect_conflict_level(items: tuple[ContextItem, ...]) -> str:
    """Analyze direction and contradictions among context items."""
    has_bullish = any(
        item.direction == "bullish" and item.severity in ("high", "critical") for item in items
    )
    has_bearish = any(
        item.direction == "bearish" and item.severity in ("high", "critical") for item in items
    )
    if has_bullish and has_bearish:
        return "HIGH"

    if any(item.contradictory or item.direction == "mixed" for item in items):
        return "MEDIUM"

    return "LOW"


class ContextEngine:
    """Live Context Engine with tiered citations, deduplication, and conflict resolution."""

    def __init__(
        self,
        *,
        search_provider: SearchProvider,
        quota_repo: QuotaRepository | None = None,
        max_daily_searches: int = 50,
    ) -> None:
        self.search_provider = search_provider
        self.quota_repo = quota_repo
        self.max_daily_searches = max_daily_searches

    async def fetch_snapshot(
        self,
        symbol: str = "PAXGUSDT",
        now: datetime | None = None,
    ) -> ContextSnapshot:
        current_time = now or datetime.now(UTC)
        date_str = current_time.strftime("%Y-%m-%d")

        # Quota enforcement
        if self.quota_repo is not None:
            allowed = self.quota_repo.consume_web_call(date_str, max_limit=self.max_daily_searches)
            if not allowed:
                # Quota exhausted: return fail-closed minimal snapshot
                return ContextSnapshot.build(
                    fetched_at=current_time,
                    sources=(),
                    items=(),
                    conflict_level="HIGH",
                )

        query = f"{symbol} gold price real yields inflation fed macro news"
        raw_results = await self.search_provider.search(query=query, max_results=10)
        sources = deduplicate_and_filter_sources(raw_results, max_per_domain=2)
        by_url = {normalize_url(item.url): item for item in raw_results}

        bullish_keywords = ("rally", "surge", "gain", "bullish", "cut", "dovish")
        bearish_keywords = ("fall", "tumble", "plunge", "bearish", "hike", "hawkish", "spike")

        items: list[ContextItem] = []
        for idx, src in enumerate(sources):
            raw = by_url.get(src.url)
            text = f"{src.title} {raw.content if raw else ''}".lower()
            direction = "neutral"
            if any(word in text for word in bullish_keywords):
                direction = "bullish"
            elif any(word in text for word in bearish_keywords):
                direction = "bearish"
            summary = (raw.content if raw and raw.content else src.title)[:400]
            items.append(
                ContextItem(
                    summary=summary or src.title[:200],
                    driver="macro",
                    direction=direction,  # type: ignore[arg-type]
                    severity="high" if src.tier <= 2 else "medium",
                    published_at=src.published_at,
                    source_indexes=(idx,),
                    contradictory=False,
                )
            )

        items_tuple = tuple(items)
        conflict_level = detect_conflict_level(items_tuple)

        return ContextSnapshot.build(
            fetched_at=current_time,
            sources=sources,
            items=items_tuple,
            conflict_level=conflict_level,
        )
