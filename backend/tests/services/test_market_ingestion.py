"""Ingestion writes only verified exchange data, and never invents a candle."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from goldguard.config import Settings
from goldguard.domain.models import Candle, Quote
from goldguard.market.binance import SymbolFilters
from goldguard.services.ingestion import MarketIngestionService
from goldguard.storage.database import Database
from goldguard.storage.repositories import MarketCandleRepository

FILTERS = SymbolFilters(
    tick_size=Decimal("0.01"),
    step_size=Decimal("0.0001"),
    minimum_quantity=Decimal("0.0001"),
    maximum_quantity=Decimal("100"),
    minimum_notional=Decimal("5"),
)


def _candles(count: int, timeframe: str, *, start: datetime) -> list[Candle]:
    minutes = 15 if timeframe == "15m" else 60
    step = timedelta(minutes=minutes)
    return [
        Candle(
            symbol="PAXGUSDT",
            timeframe=timeframe,
            open_time=start + step * index,
            close_time=start + step * (index + 1),
            open=Decimal("2500"),
            high=Decimal("2505"),
            low=Decimal("2495"),
            close=Decimal("2500"),
            volume=Decimal("10"),
            closed=True,
        )
        for index in range(count)
    ]


class _StubClient:
    """Replays a fixed series; ``fail`` makes every call raise like a network outage."""

    def __init__(self, *, fail: bool = False) -> None:
        self.fail = fail
        anchor = datetime(2026, 8, 1, tzinfo=UTC)
        self.series = {
            "15m": _candles(60, "15m", start=anchor),
            "1h": _candles(60, "1h", start=anchor),
        }

    async def symbol_filters(self, symbol: str) -> SymbolFilters:
        self._maybe_fail()
        return FILTERS

    async def quote(self, symbol: str, *, observed_at: datetime | None = None) -> Quote:
        self._maybe_fail()
        return Quote(
            bid=Decimal("2500.00"),
            ask=Decimal("2500.40"),
            observed_at=observed_at or datetime.now(UTC),
        )

    async def klines(self, *, symbol: str, interval: str, limit: int = 1000, **_: object):
        self._maybe_fail()
        return list(self.series[interval][-limit:])

    def _maybe_fail(self) -> None:
        if self.fail:
            raise RuntimeError("exchange unreachable")


class _StubRuntime:
    def __init__(self) -> None:
        self.published: list[dict[str, object]] = []

    def configure_market_inputs(self, **kwargs: object) -> None:
        self.published.append(kwargs)

    def process_closed_candle(self, *_: object) -> None:  # pragma: no cover - not exercised
        raise AssertionError("start() must not evaluate candles")

    def process_quote(self, *_: object) -> None:  # pragma: no cover - not exercised
        raise AssertionError("start() must not evaluate quotes")


@pytest.fixture
def candle_repo(tmp_path) -> MarketCandleRepository:
    database = Database(tmp_path / "ingestion.db")
    database.migrate()
    return MarketCandleRepository(database)


def _service(candle_repo, client, **overrides):
    settings = Settings(environment="test", data_dir=candle_repo.database.path.parent, **overrides)
    runtime = _StubRuntime()
    service = MarketIngestionService(
        settings=settings,
        runtime=runtime,  # type: ignore[arg-type]
        candle_repo=candle_repo,
        client=client,
    )
    return service, runtime


@pytest.mark.asyncio
async def test_warmup_persists_and_publishes_verified_candles(candle_repo) -> None:
    service, runtime = _service(candle_repo, _StubClient())
    await service.start()
    await service.aclose()

    snapshot = service.snapshot()
    assert snapshot.verified is True
    assert snapshot.source == "binance-rest"
    assert len(snapshot.candles_15m) == 60
    assert snapshot.latest_quote is not None
    assert snapshot.filters == FILTERS
    assert runtime.published, "the runtime must receive the ingested inputs"
    assert candle_repo.load_candles("PAXGUSDT", "15m", limit=100), "candles must be durable"


@pytest.mark.asyncio
async def test_unreachable_exchange_reports_unavailable_and_invents_nothing(candle_repo) -> None:
    service, _ = _service(candle_repo, _StubClient(fail=True))
    await service.start()
    await service.aclose()

    snapshot = service.snapshot()
    assert snapshot.availability == "unavailable"
    assert snapshot.verified is False
    assert snapshot.candles_15m == ()
    assert snapshot.latest_quote is None
    assert snapshot.detail is not None and "unreachable" in snapshot.detail


@pytest.mark.asyncio
async def test_disabled_ingestion_replays_persisted_candles_as_stale(candle_repo) -> None:
    seeded = _candles(60, "15m", start=datetime(2026, 8, 1, tzinfo=UTC))
    candle_repo.upsert_candles(seeded, source="fixture")

    service, _ = _service(candle_repo, _StubClient(), market_ingestion_enabled=False)
    await service.start()
    await service.aclose()

    snapshot = service.snapshot()
    assert len(snapshot.candles_15m) == 60
    assert snapshot.latest_quote is None
    assert snapshot.stale is True
    assert snapshot.availability == "degraded"
    assert snapshot.source == "sqlite-market-candles"
