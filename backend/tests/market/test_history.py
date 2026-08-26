from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from goldguard.domain.models import Candle
from goldguard.market.history import HistoryDownloader, verify_candles


def candle(opened: datetime, timeframe: str = "15m") -> Candle:
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
        closed=True,
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
