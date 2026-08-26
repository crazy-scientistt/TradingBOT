from datetime import UTC, datetime
from pathlib import Path

import pytest
from goldguard.context.engine import ContextEngine, detect_conflict_level
from goldguard.context.models import ContextItem
from goldguard.context.sources import RawSearchResult
from goldguard.storage.database import Database
from goldguard.storage.repositories import QuotaRepository


@pytest.fixture
def database(tmp_path: Path) -> Database:
    db = Database(tmp_path / "goldguard.db")
    db.migrate()
    return db


class MockSearchProvider:
    def __init__(self, results: list[RawSearchResult]) -> None:
        self._results = results

    async def search(self, query: str, max_results: int = 5) -> list[RawSearchResult]:
        return self._results


def test_detect_conflict_level() -> None:
    now = datetime(2026, 8, 26, 12, tzinfo=UTC)
    bullish_item = ContextItem(
        summary="Gold surges on rate cut",
        driver="rates",
        direction="bullish",
        severity="high",
        published_at=now,
        source_indexes=(0,),
        contradictory=False,
    )
    bearish_item = ContextItem(
        summary="Gold plunges on strong dollar",
        driver="dollar",
        direction="bearish",
        severity="high",
        published_at=now,
        source_indexes=(1,),
        contradictory=False,
    )
    neutral_item = ContextItem(
        summary="Gold holds steady",
        driver="rates",
        direction="neutral",
        severity="low",
        published_at=now,
        source_indexes=(0,),
        contradictory=False,
    )

    # Bullish + Bearish = HIGH conflict
    assert detect_conflict_level((bullish_item, bearish_item)) == "HIGH"
    # Single direction = LOW conflict
    assert detect_conflict_level((bullish_item, neutral_item)) == "LOW"
    # Contradictory flag = MEDIUM conflict
    mild_item = ContextItem(
        summary="Mixed signals",
        driver="rates",
        direction="mixed",
        severity="medium",
        published_at=now,
        source_indexes=(0,),
        contradictory=True,
    )
    assert detect_conflict_level((mild_item,)) == "MEDIUM"


@pytest.mark.asyncio
async def test_context_engine_quota_and_snapshot_generation(database: Database) -> None:
    quota_repo = QuotaRepository(database)
    raw = [
        RawSearchResult(
            "https://www.reuters.com/markets/gold-rallies",
            "Gold Rallies on Fed Pause",
            "Content",
        ),
        RawSearchResult(
            "https://www.federalreserve.gov/press",
            "Fed Holds Rates",
            "Content",
        ),
    ]
    provider = MockSearchProvider(raw)
    engine = ContextEngine(search_provider=provider, quota_repo=quota_repo, max_daily_searches=2)

    now = datetime(2026, 8, 26, 12, tzinfo=UTC)
    # First search succeeds
    snap1 = await engine.fetch_snapshot(symbol="PAXGUSDT", now=now)
    assert len(snap1.sources) == 2
    assert snap1.conflict_level in ("LOW", "MEDIUM", "HIGH")

    # Second search succeeds
    snap2 = await engine.fetch_snapshot(symbol="PAXGUSDT", now=now)
    assert len(snap2.sources) == 2

    # Third search exceeds daily quota of 2 -> fail closed with empty sources and HIGH conflict
    snap3 = await engine.fetch_snapshot(symbol="PAXGUSDT", now=now)
    assert len(snap3.sources) == 0
    assert snap3.conflict_level == "HIGH"
