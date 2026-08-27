from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path

import pytest
from goldguard.domain.models import Candle
from goldguard.market.dataset_service import DatasetProgress, DatasetService
from goldguard.market.history import DatasetStatus


def _candle(opened: datetime, timeframe: str = "15m", *, closed: bool = True) -> Candle:
    interval = timedelta(minutes=15 if timeframe == "15m" else 60)
    return Candle(
        symbol="PAXGUSDT",
        timeframe=timeframe,
        open_time=opened,
        close_time=opened + interval - timedelta(milliseconds=1),
        open=Decimal("2500"),
        high=Decimal("2505"),
        low=Decimal("2495"),
        close=Decimal("2502"),
        volume=Decimal("10"),
        closed=closed,
    )


class _PagedClient:
    def __init__(self, rows: dict[str, list[Candle]], *, fail_once: bool = False) -> None:
        self.rows = rows
        self.calls: list[tuple[str, int | None]] = []
        self.fail_once = fail_once
        self.failures = 0

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
        del symbol, now_ms
        self.calls.append((interval, start_time_ms))
        if self.fail_once and self.failures == 0:
            self.failures += 1
            raise RuntimeError("temporary exchange failure")
        start = datetime.fromtimestamp(start_time_ms / 1000, tz=UTC) if start_time_ms else None
        end = datetime.fromtimestamp(end_time_ms / 1000, tz=UTC) if end_time_ms else None
        values = [
            row
            for row in self.rows[interval]
            if (start is None or row.open_time >= start)
            and (end is None or row.open_time < end)
        ]
        # Small pages make resumability observable in the tests.
        return values[: min(limit, 2)]


def _rows(start: datetime, end: datetime) -> dict[str, list[Candle]]:
    result: dict[str, list[Candle]] = {}
    for timeframe, minutes in (("15m", 15), ("1h", 60)):
        current = start
        result[timeframe] = []
        while current < end:
            result[timeframe].append(_candle(current, timeframe))
            current += timedelta(minutes=minutes)
    return result


@pytest.mark.asyncio
async def test_bootstrap_resumes_partial_pages_and_persists_progress(tmp_path: Path) -> None:
    start = datetime(2026, 8, 25, tzinfo=UTC)
    end = start + timedelta(hours=4)
    rows = _rows(start - timedelta(days=1), end)
    first_client = _PagedClient(rows)
    original_klines = first_client.klines

    async def fail_after_first_page(
        *,
        symbol: str,
        interval: str,
        start_time_ms: int | None = None,
        end_time_ms: int | None = None,
        limit: int = 1000,
        now_ms: int | None = None,
    ) -> list[Candle]:
        if len(first_client.calls) >= 1:
            raise RuntimeError("interrupted bootstrap")
        return await original_klines(
            symbol=symbol,
            interval=interval,
            start_time_ms=start_time_ms,
            end_time_ms=end_time_ms,
            limit=limit,
            now_ms=now_ms,
        )

    first_client.klines = fail_after_first_page  # type: ignore[method-assign]
    service = DatasetService(
        client=first_client,
        storage_dir=tmp_path,
        warmup_days=1,
        timeframes=("15m", "1h"),
        max_attempts=1,
        backoff_base_seconds=0,
    )
    with pytest.raises(RuntimeError, match="history request failed"):
        await service.bootstrap("PAXGUSDT", start, end)

    progress_path = tmp_path / "market" / "PAXGUSDT" / "progress.json"
    assert json.loads(progress_path.read_text(encoding="utf-8"))["status"] == "DOWNLOADING"

    resumed_client = _PagedClient(rows)
    resumed = DatasetService(
        client=resumed_client,
        storage_dir=tmp_path,
        warmup_days=1,
        timeframes=("15m", "1h"),
        max_attempts=1,
        backoff_base_seconds=0,
    )
    manifest = await resumed.bootstrap("PAXGUSDT", start, end)

    assert manifest.status is DatasetStatus.VERIFIED
    assert resumed.status("PAXGUSDT") is DatasetStatus.VERIFIED
    # The first timeframe's first page was checkpointed, so the resumed run starts later.
    assert resumed_client.calls[0][1] is not None
    assert resumed_client.calls[0][1] > int((start - timedelta(days=1)).timestamp() * 1000)


@pytest.mark.asyncio
async def test_checksum_tampering_demotes_verified_dataset(tmp_path: Path) -> None:
    start = datetime(2026, 8, 25, tzinfo=UTC)
    end = start + timedelta(hours=2)
    service = DatasetService(
        client=_PagedClient(_rows(start, end)),
        storage_dir=tmp_path,
        warmup_days=0,
        timeframes=("15m", "1h"),
        max_attempts=1,
        backoff_base_seconds=0,
    )
    await service.bootstrap("PAXGUSDT", start, end)
    path = tmp_path / "market" / "PAXGUSDT" / "15m_20260825_20260825.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload[0]["close"] = "2510"
    path.write_text(json.dumps(payload), encoding="utf-8")

    assert service.status("PAXGUSDT") is DatasetStatus.CORRUPT
    with pytest.raises(RuntimeError, match="verified"):
        service.load_verified("PAXGUSDT", "15m")


@pytest.mark.asyncio
async def test_forming_candles_are_not_persisted_and_progress_is_visible(tmp_path: Path) -> None:
    start = datetime(2026, 8, 25, tzinfo=UTC)
    end = start + timedelta(hours=1)
    rows = _rows(start, end)
    rows["15m"].append(_candle(end, "15m", closed=False))
    progress: list[DatasetProgress] = []

    service = DatasetService(
        client=_PagedClient(rows),
        storage_dir=tmp_path,
        warmup_days=0,
        timeframes=("15m", "1h"),
        max_attempts=1,
        backoff_base_seconds=0,
        progress_callback=progress.append,
    )
    manifest = await service.bootstrap("PAXGUSDT", start, end)

    assert manifest.status is DatasetStatus.VERIFIED
    assert progress
    assert progress[-1].status is DatasetStatus.VERIFIED
    assert progress[-1].percent == 100
    stored = json.loads(
        (tmp_path / "market" / "PAXGUSDT" / "15m_20260825_20260825.json").read_text(
            encoding="utf-8"
        )
    )
    assert all(row["closed"] is True for row in stored)


@pytest.mark.asyncio
async def test_transient_page_failures_retry_with_backoff(tmp_path: Path) -> None:
    start = datetime(2026, 8, 25, tzinfo=UTC)
    end = start + timedelta(hours=1)
    client = _PagedClient(_rows(start, end), fail_once=True)
    service = DatasetService(
        client=client,
        storage_dir=tmp_path,
        warmup_days=0,
        timeframes=("15m",),
        max_attempts=2,
        backoff_base_seconds=0,
    )

    manifest = await service.bootstrap("PAXGUSDT", start, end)

    assert manifest.status is DatasetStatus.VERIFIED
    assert client.failures == 1
    assert len(client.calls) >= 2
