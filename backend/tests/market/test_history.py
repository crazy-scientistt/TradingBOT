from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path

import pytest
from goldguard.domain.models import Candle
from goldguard.market.history import (
    BootstrapManifest,
    DatasetStatus,
    HistoryDownloader,
    bootstrap_history,
    verify_candles,
)


def candle(opened: datetime, timeframe: str = "15m", closed: bool = True) -> Candle:
    minutes = 15 if timeframe == "15m" else 60
    return Candle(
        symbol="PAXGUSDT",
        timeframe=timeframe,
        open_time=opened,
        close_time=opened + timedelta(minutes=minutes) - timedelta(milliseconds=1),
        open=Decimal("2500"),
        high=Decimal("2505"),
        low=Decimal("2495"),
        close=Decimal("2502"),
        volume=Decimal("10"),
        closed=closed,
    )


def test_verify_candles_detects_gaps_duplicates_and_bad_ohlc() -> None:
    start = datetime(2026, 8, 26, tzinfo=UTC)
    complete = [candle(start), candle(start + timedelta(minutes=15))]
    assert verify_candles(complete, "15m").verified is True

    gap = [candle(start), candle(start + timedelta(minutes=30))]
    assert verify_candles(gap, "15m").missing_intervals == 1
    assert verify_candles(gap, "15m").verified is False

    duplicate = [candle(start), candle(start)]
    assert verify_candles(duplicate, "15m").duplicate_intervals == 1
    assert verify_candles(duplicate, "15m").verified is False


@pytest.mark.asyncio
async def test_downloader_paginates_without_duplicating_boundaries() -> None:
    start = datetime(2026, 8, 26, tzinfo=UTC)
    rows = [candle(start + timedelta(minutes=15 * index)) for index in range(3)]

    class FakeClient:
        def __init__(self) -> None:
            self.calls: list[int | None] = []

        async def klines(
            self,
            *,
            symbol: str,
            interval: str,
            start_time_ms: int | None = None,
            end_time_ms: int | None = None,
            limit: int = 1000,
            now_ms: int | None = None,
        ) -> list[Candle]:
            del symbol, interval, end_time_ms, limit, now_ms
            self.calls.append(start_time_ms)
            if len(self.calls) == 1:
                return rows[:2]
            if len(self.calls) == 2:
                return rows[1:]
            return []

    downloader = HistoryDownloader(FakeClient())
    result = await downloader.fetch(
        symbol="PAXGUSDT",
        timeframe="15m",
        start=start,
        end=start + timedelta(hours=1),
    )

    assert [row.open_time for row in result.candles] == [row.open_time for row in rows]
    assert result.manifest.duplicate_intervals == 0
    assert result.manifest.checksum


@pytest.mark.asyncio
async def test_bootstrap_history_warmup_and_resumable(tmp_path: Path) -> None:
    start = datetime(2026, 8, 26, tzinfo=UTC)
    end = start + timedelta(days=2)
    warmup_days = 1

    # Generate synthetic 15m and 1h candles covering (start - 1 day) to end
    actual_start = start - timedelta(days=warmup_days)

    def generate_series(tf: str) -> list[Candle]:
        step = timedelta(minutes=15 if tf == "15m" else 60)
        curr = actual_start
        series: list[Candle] = []
        while curr < end:
            series.append(candle(curr, timeframe=tf))
            curr += step
        return series

    series_15m = generate_series("15m")
    series_1h = generate_series("1h")

    class MockKlineClient:
        async def klines(
            self,
            *,
            symbol: str,
            interval: str,
            start_time_ms: int | None = None,
            end_time_ms: int | None = None,
            limit: int = 1000,
            now_ms: int | None = None,
        ) -> list[Candle]:
            source = series_15m if interval == "15m" else series_1h
            start_dt = (
                datetime.fromtimestamp(start_time_ms / 1000, tz=UTC)
                if start_time_ms
                else actual_start
            )
            end_dt = (
                datetime.fromtimestamp(end_time_ms / 1000, tz=UTC)
                if end_time_ms
                else end
            )
            return [c for c in source if start_dt <= c.open_time < end_dt][:limit]

    client = MockKlineClient()

    # Initial bootstrap
    manifest = await bootstrap_history(
        symbol="PAXGUSDT",
        start=start,
        end=end,
        timeframes=("15m", "1h"),
        warmup_days=warmup_days,
        client=client,
        storage_dir=tmp_path,
    )

    assert isinstance(manifest, BootstrapManifest)
    assert manifest.status == DatasetStatus.VERIFIED
    assert manifest.warmup_included is True
    assert "15m" in manifest.timeframe_checksums
    assert "1h" in manifest.timeframe_checksums

    # Resuming should verify existing files without re-fetching
    resume_manifest = await bootstrap_history(
        symbol="PAXGUSDT",
        start=start,
        end=end,
        timeframes=("15m", "1h"),
        warmup_days=warmup_days,
        client=client,
        storage_dir=tmp_path,
    )
    assert resume_manifest.status == DatasetStatus.VERIFIED
    assert resume_manifest.checksum == manifest.checksum
