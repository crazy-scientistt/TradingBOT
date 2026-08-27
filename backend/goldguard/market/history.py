import hashlib
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from typing import Protocol

from goldguard.domain.models import Candle

INTERVAL_MILLISECONDS = {"15m": 15 * 60 * 1000, "1h": 60 * 60 * 1000}


class DatasetStatus(StrEnum):
    DOWNLOADING = "DOWNLOADING"
    VERIFIED = "VERIFIED"
    CORRUPT = "CORRUPT"


@dataclass(frozen=True)
class VerificationResult:
    verified: bool
    missing_intervals: int
    duplicate_intervals: int


@dataclass(frozen=True)
class DatasetManifest:
    symbol: str
    timeframe: str
    requested_start: datetime
    requested_end: datetime
    actual_start: datetime | None
    actual_end: datetime | None
    candle_count: int
    missing_intervals: int
    duplicate_intervals: int
    checksum: str
    verified: bool


@dataclass(frozen=True)
class BootstrapManifest:
    symbol: str
    requested_start: datetime
    requested_end: datetime
    actual_start: datetime
    actual_end: datetime
    warmup_days: int
    warmup_included: bool
    status: DatasetStatus
    timeframe_checksums: dict[str, str]
    timeframe_counts: dict[str, int]
    checksum: str
    created_at: str
    progress_percent: int = 100
    last_error: str | None = None
    timeframe_ranges: dict[str, tuple[str, str]] | None = None


@dataclass(frozen=True)
class HistoryResult:
    candles: tuple[Candle, ...]
    manifest: DatasetManifest


class KlineClient(Protocol):
    async def klines(
        self,
        *,
        symbol: str,
        interval: str,
        start_time_ms: int | None = None,
        end_time_ms: int | None = None,
        limit: int = 1000,
        now_ms: int | None = None,
    ) -> list[Candle]: ...


def verify_candles(
    candles: list[Candle] | tuple[Candle, ...],
    timeframe: str,
) -> VerificationResult:
    interval_ms = INTERVAL_MILLISECONDS[timeframe]
    ordered = sorted(candles, key=lambda item: item.open_time)
    seen: set[datetime] = set()
    duplicates = 0
    missing = 0
    previous: datetime | None = None
    for item in ordered:
        if (
            item.timeframe != timeframe
            or not item.closed
            or item.close_time <= item.open_time
            or item.high < max(item.open, item.close, item.low)
            or item.low > min(item.open, item.close, item.high)
        ):
            return VerificationResult(False, missing, duplicates)
        if item.open_time in seen:
            duplicates += 1
            continue
        seen.add(item.open_time)
        if previous is not None:
            elapsed_ms = int((item.open_time - previous).total_seconds() * 1000)
            if elapsed_ms > interval_ms:
                missing += (elapsed_ms // interval_ms) - 1
            elif elapsed_ms != interval_ms:
                return VerificationResult(False, missing, duplicates)
        previous = item.open_time
    verified = bool(ordered) and missing == 0 and duplicates == 0
    return VerificationResult(verified, missing, duplicates)


def _datetime_to_ms(value: datetime) -> int:
    if value.tzinfo is None:
        raise ValueError("history boundaries must be timezone-aware")
    return int(value.astimezone(UTC).timestamp() * 1000)


def _checksum(candles: tuple[Candle, ...]) -> str:
    digest = hashlib.sha256()
    for item in candles:
        digest.update(
            "|".join(
                (
                    item.symbol,
                    item.timeframe,
                    item.open_time.isoformat(),
                    str(item.open),
                    str(item.high),
                    str(item.low),
                    str(item.close),
                    str(item.volume),
                )
            ).encode()
        )
        digest.update(b"\n")
    return digest.hexdigest()


def checksum_candles(candles: list[Candle] | tuple[Candle, ...]) -> str:
    """Return the stable row checksum used by dataset manifests.

    The public helper keeps checksum calculation in one place for both the
    downloader and the resumable dataset service.  Rows are expected to be in
    chronological order; callers loading a file should sort before calling it.
    """

    return _checksum(tuple(candles))


class HistoryDownloader:
    def __init__(self, client: KlineClient) -> None:
        self.client = client

    async def fetch(
        self,
        *,
        symbol: str,
        timeframe: str,
        start: datetime,
        end: datetime,
    ) -> HistoryResult:
        interval_ms = INTERVAL_MILLISECONDS[timeframe]
        cursor = _datetime_to_ms(start)
        end_ms = _datetime_to_ms(end)
        by_open_time: dict[datetime, Candle] = {}
        while cursor < end_ms:
            page = await self.client.klines(
                symbol=symbol,
                interval=timeframe,
                start_time_ms=cursor,
                end_time_ms=end_ms,
                limit=1000,
                now_ms=end_ms + interval_ms,
            )
            if not page:
                break
            for item in page:
                if start <= item.open_time < end and item.closed:
                    by_open_time.setdefault(item.open_time, item)
            last_open_ms = max(_datetime_to_ms(item.open_time) for item in page)
            next_cursor = last_open_ms + interval_ms
            if next_cursor <= cursor:
                raise RuntimeError("Binance history pagination made no progress")
            cursor = next_cursor

        candles = tuple(sorted(by_open_time.values(), key=lambda item: item.open_time))
        verification = verify_candles(candles, timeframe)
        manifest = DatasetManifest(
            symbol=symbol,
            timeframe=timeframe,
            requested_start=start,
            requested_end=end,
            actual_start=candles[0].open_time if candles else None,
            actual_end=candles[-1].close_time if candles else None,
            candle_count=len(candles),
            missing_intervals=verification.missing_intervals,
            duplicate_intervals=verification.duplicate_intervals,
            checksum=_checksum(candles),
            verified=verification.verified,
        )
        return HistoryResult(candles=candles, manifest=manifest)


async def bootstrap_history(
    *,
    symbol: str,
    start: datetime,
    end: datetime,
    timeframes: tuple[str, ...] = ("15m", "1h"),
    warmup_days: int = 30,
    client: KlineClient,
    storage_dir: Path,
) -> BootstrapManifest:
    """Compatibility wrapper around :class:`DatasetService`.

    Keeping this function preserves the original script and callers while the
    service owns checkpointing, verification, retries, and status reads.
    """

    from goldguard.market.dataset_service import DatasetService

    service = DatasetService(
        client=client,
        storage_dir=storage_dir,
        timeframes=timeframes,
        warmup_days=warmup_days,
    )
    return await service.bootstrap(symbol, start, end)
