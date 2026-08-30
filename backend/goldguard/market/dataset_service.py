"""Resumable, fail-closed historical market dataset management.

The service is deliberately independent of the runtime and backtest engines. It
only makes a dataset available after every requested timeframe has a complete,
closed-candle series whose on-disk rows match the persisted checksums.
"""

from __future__ import annotations

import asyncio
import hashlib
import inspect
import json
from collections.abc import Awaitable, Callable
from dataclasses import asdict, dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import cast

from goldguard.domain.models import Candle
from goldguard.market.history import (
    INTERVAL_MILLISECONDS,
    BootstrapManifest,
    DatasetStatus,
    KlineClient,
    VerificationResult,
    checksum_candles,
    verify_candles,
)

ProgressCallback = Callable[["DatasetProgress"], object | Awaitable[object] | None]


@dataclass(frozen=True)
class DatasetProgress:
    """Durable and callback-visible bootstrap progress for one symbol."""

    symbol: str
    status: DatasetStatus
    timeframe: str | None
    downloaded_candles: int
    expected_candles: int
    percent: int
    updated_at: str
    error: str | None = None


def _utc(value: datetime, *, name: str) -> datetime:
    if value.tzinfo is None or value.utcoffset() != UTC.utcoffset(value):
        raise ValueError(f"{name} must be timezone-aware UTC")
    return value.astimezone(UTC)


def _to_ms(value: datetime) -> int:
    return int(value.astimezone(UTC).timestamp() * 1000)


def _range_name(actual_start: datetime, end: datetime) -> str:
    # Retain the established file naming convention used by existing tooling.
    return f"{actual_start:%Y%m%d}_{end:%Y%m%d}"


def _atomic_json_write(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(f".{path.name}.tmp")
    temp.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    temp.replace(path)


def _read_candles(path: Path) -> list[Candle]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, list):
        raise ValueError(f"{path.name} does not contain a candle list")
    return [Candle.model_validate(item) for item in raw]


def _ohlcv_conflict(left: Candle, right: Candle) -> bool:
    return (
        left.open != right.open
        or left.high != right.high
        or left.low != right.low
        or left.close != right.close
        or left.volume != right.volume
    )


def _align_up(value: datetime, interval_ms: int) -> datetime:
    millis = _to_ms(value)
    aligned = ((millis + interval_ms - 1) // interval_ms) * interval_ms
    return datetime.fromtimestamp(aligned / 1000, tz=UTC)


def _align_down(value: datetime, interval_ms: int) -> datetime:
    millis = _to_ms(value)
    aligned = (millis // interval_ms) * interval_ms
    return datetime.fromtimestamp(aligned / 1000, tz=UTC)


def _manifest_payload(manifest: BootstrapManifest) -> dict[str, object]:
    return {
        "symbol": manifest.symbol,
        "requested_start": manifest.requested_start.isoformat(),
        "requested_end": manifest.requested_end.isoformat(),
        "actual_start": manifest.actual_start.isoformat(),
        "actual_end": manifest.actual_end.isoformat(),
        "warmup_days": manifest.warmup_days,
        "warmup_included": manifest.warmup_included,
        "status": manifest.status.value,
        "timeframe_checksums": manifest.timeframe_checksums,
        "timeframe_counts": manifest.timeframe_counts,
        "checksum": manifest.checksum,
        "created_at": manifest.created_at,
        "progress_percent": manifest.progress_percent,
        "last_error": manifest.last_error,
        "timeframe_ranges": manifest.timeframe_ranges or {},
    }


class DatasetService:
    """Bootstrap and read verified historical candles.

    ``client`` is a Binance-compatible public client. The service checkpoints
    each page to a ``.partial`` file, so a process interruption resumes from the
    first missing interval. Progress is written to ``progress.json`` and also
    sent to the optional callback, making a long three-year run observable.
    """

    def __init__(
        self,
        client: KlineClient,
        storage_dir: Path,
        *,
        timeframes: tuple[str, ...] = ("15m", "1h"),
        warmup_days: int = 30,
        max_attempts: int = 3,
        backoff_base_seconds: float = 0.2,
        sleep: Callable[[float], Awaitable[object]] = asyncio.sleep,
        progress_callback: ProgressCallback | None = None,
    ) -> None:
        if not timeframes:
            raise ValueError("at least one timeframe is required")
        if any(item not in INTERVAL_MILLISECONDS for item in timeframes):
            raise ValueError("unsupported timeframe")
        if warmup_days < 0:
            raise ValueError("warmup_days must be non-negative")
        if max_attempts < 1:
            raise ValueError("max_attempts must be positive")
        if backoff_base_seconds < 0:
            raise ValueError("backoff_base_seconds must be non-negative")
        self._client = client
        self._storage_dir = storage_dir
        self._timeframes = tuple(dict.fromkeys(timeframes))
        self._warmup_days = warmup_days
        self._max_attempts = max_attempts
        self._backoff_base_seconds = backoff_base_seconds
        self._sleep = sleep
        self._progress_callback = progress_callback

    async def bootstrap(
        self,
        symbol: str,
        start: datetime,
        end: datetime,
    ) -> BootstrapManifest:
        """Download, checkpoint, verify, and manifest a multi-timeframe dataset."""

        if not symbol.strip():
            raise ValueError("symbol must not be empty")
        requested_start = _utc(start, name="start")
        requested_end = _utc(end, name="end")
        if requested_end <= requested_start:
            raise ValueError("end must be after start")
        # Snap to 1h boundaries so Binance kline open times match expected counts.
        hour_ms = INTERVAL_MILLISECONDS["1h"]
        requested_start = _align_up(requested_start, hour_ms)
        requested_end = _align_down(requested_end, hour_ms)
        if requested_end <= requested_start:
            raise ValueError("end must be after start after interval alignment")
        actual_start = requested_start - timedelta(days=self._warmup_days)
        dataset_dir = self._storage_dir / "market" / symbol
        dataset_dir.mkdir(parents=True, exist_ok=True)
        manifest_path = dataset_dir / "manifest.json"
        progress_path = dataset_dir / "progress.json"
        range_name = _range_name(actual_start, requested_end)

        total_expected = sum(
            self._expected_count(actual_start, requested_end, timeframe)
            for timeframe in self._timeframes
        )
        # Publish a provisional manifest before the first request. This makes
        # an interrupted run visible to status readers even when an older
        # verified manifest exists for the same symbol.
        provisional = BootstrapManifest(
            symbol=symbol,
            requested_start=requested_start,
            requested_end=requested_end,
            actual_start=actual_start,
            actual_end=requested_end,
            warmup_days=self._warmup_days,
            warmup_included=self._warmup_days > 0,
            status=DatasetStatus.DOWNLOADING,
            timeframe_checksums={},
            timeframe_counts={},
            checksum=self._combined_checksum({}),
            created_at=datetime.now(UTC).isoformat(),
            progress_percent=0,
            timeframe_ranges={
                timeframe: (actual_start.isoformat(), requested_end.isoformat())
                for timeframe in self._timeframes
            },
        )
        _atomic_json_write(manifest_path, _manifest_payload(provisional))
        await self._emit(
            DatasetProgress(
                symbol=symbol,
                status=DatasetStatus.DOWNLOADING,
                timeframe=None,
                downloaded_candles=0,
                expected_candles=total_expected,
                percent=0,
                updated_at=datetime.now(UTC).isoformat(),
            ),
            progress_path,
        )

        tf_checksums: dict[str, str] = {}
        tf_counts: dict[str, int] = {}
        tf_ranges: dict[str, tuple[str, str]] = {
            timeframe: (actual_start.isoformat(), requested_end.isoformat())
            for timeframe in self._timeframes
        }
        completed = 0
        last_error: str | None = None
        try:
            for timeframe in self._timeframes:
                final_path = dataset_dir / f"{timeframe}_{range_name}.json"
                partial_path = final_path.with_name(f"{final_path.name}.partial")
                expected = self._expected_count(actual_start, requested_end, timeframe)
                candles, duplicate_detected = self._load_existing(
                    final_path, partial_path, symbol=symbol, timeframe=timeframe
                )
                if final_path.exists() and not partial_path.exists() and self._is_verified_series(
                    candles,
                    symbol=symbol,
                    timeframe=timeframe,
                    actual_start=actual_start,
                    end=requested_end,
                    expected=expected,
                    duplicate_detected=duplicate_detected,
                ):
                    tf_checksums[timeframe] = checksum_candles(candles)
                    tf_counts[timeframe] = len(candles)
                    completed += len(candles)
                    await self._emit_progress(
                        progress_path,
                        symbol=symbol,
                        status=DatasetStatus.DOWNLOADING,
                        timeframe=timeframe,
                        downloaded=completed,
                        expected=total_expected,
                    )
                    continue

                # A corrupt final file is never used as a resumable seed. A
                # partial checkpoint, when present, remains the source of truth.
                if final_path.exists() and not partial_path.exists():
                    candles = []
                    duplicate_detected = False

                fetched, duplicate_detected = await self._download_timeframe(
                    symbol=symbol,
                    timeframe=timeframe,
                    actual_start=actual_start,
                    end=requested_end,
                    partial_path=partial_path,
                    seed=candles,
                    duplicate_detected=duplicate_detected,
                    progress_path=progress_path,
                    completed_before=completed,
                    total_expected=total_expected,
                )
                verification = self._verify_series(
                    fetched,
                    symbol=symbol,
                    timeframe=timeframe,
                    actual_start=actual_start,
                    end=requested_end,
                    expected=expected,
                    duplicate_detected=duplicate_detected,
                )
                if verification.verified:
                    _atomic_json_write(
                        final_path,
                        [item.model_dump(mode="json") for item in fetched],
                    )
                    partial_path.unlink(missing_ok=True)
                tf_checksums[timeframe] = checksum_candles(fetched)
                tf_counts[timeframe] = len(fetched)
                completed += len(fetched)
                if not verification.verified:
                    last_error = (
                        f"{timeframe} failed verification: "
                        f"missing={verification.missing_intervals}, "
                        f"duplicates={verification.duplicate_intervals}"
                    )

            verified = last_error is None and all(
                tf_counts.get(timeframe)
                == self._expected_count(actual_start, requested_end, timeframe)
                for timeframe in self._timeframes
            )
            status = DatasetStatus.VERIFIED if verified else DatasetStatus.CORRUPT
            combined_hash = self._combined_checksum(tf_checksums)
            manifest = BootstrapManifest(
                symbol=symbol,
                requested_start=requested_start,
                requested_end=requested_end,
                actual_start=actual_start,
                actual_end=requested_end,
                warmup_days=self._warmup_days,
                warmup_included=self._warmup_days > 0,
                status=status,
                timeframe_checksums=tf_checksums,
                timeframe_counts=tf_counts,
                checksum=combined_hash,
                created_at=datetime.now(UTC).isoformat(),
                progress_percent=(
                    100 if verified else min(99, self._percent(completed, total_expected))
                ),
                last_error=last_error,
                timeframe_ranges=tf_ranges,
            )
            _atomic_json_write(manifest_path, _manifest_payload(manifest))
            await self._emit_progress(
                progress_path,
                symbol=symbol,
                status=status,
                timeframe=None,
                downloaded=completed,
                expected=total_expected,
                error=last_error,
            )
            return manifest
        except Exception as exc:
            last_error = str(exc)
            previous_progress = self.progress(symbol)
            await self._emit_progress(
                progress_path,
                symbol=symbol,
                status=DatasetStatus.DOWNLOADING,
                timeframe=None,
                downloaded=(
                    previous_progress.downloaded_candles
                    if previous_progress is not None
                    else completed
                ),
                expected=total_expected,
                error=last_error,
            )
            raise

    def status(self, symbol: str) -> DatasetStatus:
        """Return the persisted status, rechecking verified rows and checksums."""

        dataset_dir = self._storage_dir / "market" / symbol
        manifest_path = dataset_dir / "manifest.json"
        if manifest_path.exists():
            try:
                payload = json.loads(manifest_path.read_text(encoding="utf-8"))
                status = DatasetStatus(str(payload["status"]))
                if status is not DatasetStatus.VERIFIED:
                    return status
                if str(payload.get("symbol")) != symbol:
                    return DatasetStatus.CORRUPT
                checksums = payload["timeframe_checksums"]
                counts = payload["timeframe_counts"]
                if not isinstance(checksums, dict) or not isinstance(counts, dict):
                    return DatasetStatus.CORRUPT
                manifest_timeframes = tuple(str(item) for item in checksums)
                if any(timeframe not in manifest_timeframes for timeframe in self._timeframes):
                    return DatasetStatus.CORRUPT
                actual_start = _utc(
                    datetime.fromisoformat(payload["actual_start"]), name="actual_start"
                )
                requested_end = _utc(
                    datetime.fromisoformat(payload["requested_end"]), name="requested_end"
                )
                for timeframe in manifest_timeframes:
                    filename = f"{timeframe}_{_range_name(actual_start, requested_end)}.json"
                    path = dataset_dir / filename
                    candles = _read_candles(path)
                    if len(candles) != int(counts[timeframe]):
                        return DatasetStatus.CORRUPT
                    if checksum_candles(candles) != str(checksums[timeframe]):
                        return DatasetStatus.CORRUPT
                    expected = self._expected_count(
                        actual_start,
                        requested_end,
                        timeframe,
                    )
                    if not self._is_verified_series(
                        candles,
                        symbol=symbol,
                        timeframe=timeframe,
                        actual_start=actual_start,
                        end=requested_end,
                        expected=expected,
                        duplicate_detected=False,
                    ):
                        return DatasetStatus.CORRUPT
                if self._combined_checksum(
                    {timeframe: str(checksums[timeframe]) for timeframe in manifest_timeframes}
                ) != str(payload.get("checksum")):
                    return DatasetStatus.CORRUPT
                return DatasetStatus.VERIFIED
            except (KeyError, TypeError, ValueError, OSError, json.JSONDecodeError):
                return DatasetStatus.CORRUPT
        progress_path = dataset_dir / "progress.json"
        if progress_path.exists():
            try:
                payload = json.loads(progress_path.read_text(encoding="utf-8"))
                return DatasetStatus(str(payload["status"]))
            except (KeyError, TypeError, ValueError, OSError, json.JSONDecodeError):
                return DatasetStatus.CORRUPT
        return DatasetStatus.CORRUPT

    def progress(self, symbol: str) -> DatasetProgress | None:
        """Read the latest durable progress snapshot, if a bootstrap has run."""

        path = self._storage_dir / "market" / symbol / "progress.json"
        if not path.exists():
            return None
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            return DatasetProgress(
                symbol=str(payload["symbol"]),
                status=DatasetStatus(str(payload["status"])),
                timeframe=cast(str | None, payload.get("timeframe")),
                downloaded_candles=int(payload["downloaded_candles"]),
                expected_candles=int(payload["expected_candles"]),
                percent=int(payload["percent"]),
                updated_at=str(payload["updated_at"]),
                error=cast(str | None, payload.get("error")),
            )
        except (KeyError, TypeError, ValueError, OSError, json.JSONDecodeError):
            return None

    def heal_corrupt(self, symbol: str) -> BootstrapManifest | None:
        """Recover a CORRUPT dataset caused by page-overlap flags or unaligned bounds.

        Unique, contiguous, OHLC-valid series are rewritten with a fresh checksum
        and marked VERIFIED. Internally inconsistent rows stay CORRUPT.
        """

        dataset_dir = self._storage_dir / "market" / symbol
        manifest_path = dataset_dir / "manifest.json"
        if not manifest_path.exists():
            return None
        try:
            payload = json.loads(manifest_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None
        if str(payload.get("status")) == DatasetStatus.VERIFIED.value:
            return None

        series: dict[str, list[Candle]] = {}
        for timeframe in self._timeframes:
            finals = [
                path
                for path in sorted(dataset_dir.glob(f"{timeframe}_*.json"))
                if not path.name.endswith(".partial")
            ]
            partials = sorted(dataset_dir.glob(f"{timeframe}_*.json.partial"))
            matches = finals or partials
            if not matches:
                return None
            try:
                candles = _read_candles(matches[-1])
            except (OSError, ValueError, TypeError, json.JSONDecodeError):
                return None
            unique: dict[datetime, Candle] = {}
            for item in candles:
                if item.timeframe != timeframe or item.symbol != symbol or not item.closed:
                    continue
                prior = unique.get(item.open_time)
                if prior is not None and _ohlcv_conflict(prior, item):
                    return None
                unique.setdefault(item.open_time, item)
            ordered = sorted(unique.values(), key=lambda row: row.open_time)
            verification = verify_candles(ordered, timeframe)
            if not verification.verified or not ordered:
                return None
            series[timeframe] = ordered

        bound_tf = "1h" if "1h" in series else next(iter(series))
        bound_rows = series[bound_tf]
        bound_interval = INTERVAL_MILLISECONDS[bound_tf]
        actual_start = bound_rows[0].open_time
        requested_end = bound_rows[-1].open_time + timedelta(milliseconds=bound_interval)
        trimmed: dict[str, list[Candle]] = {}
        for timeframe, rows in series.items():
            clipped = [row for row in rows if actual_start <= row.open_time < requested_end]
            verification = verify_candles(clipped, timeframe)
            if not verification.verified or not clipped:
                return None
            expected = self._expected_count(actual_start, requested_end, timeframe)
            if expected and len(clipped) != expected:
                return None
            trimmed[timeframe] = clipped
        series = trimmed
        tf_checksums = {tf: checksum_candles(rows) for tf, rows in series.items()}
        tf_counts = {tf: len(rows) for tf, rows in series.items()}
        range_name = _range_name(actual_start, requested_end)
        for timeframe, rows in series.items():
            _atomic_json_write(
                dataset_dir / f"{timeframe}_{range_name}.json",
                [item.model_dump(mode="json") for item in rows],
            )
            for leftover in dataset_dir.glob(f"{timeframe}_*.json.partial"):
                leftover.unlink(missing_ok=True)
        manifest = BootstrapManifest(
            symbol=symbol,
            requested_start=actual_start,
            requested_end=requested_end,
            actual_start=actual_start,
            actual_end=requested_end,
            warmup_days=self._warmup_days,
            warmup_included=self._warmup_days > 0,
            status=DatasetStatus.VERIFIED,
            timeframe_checksums=tf_checksums,
            timeframe_counts=tf_counts,
            checksum=self._combined_checksum(tf_checksums),
            created_at=datetime.now(UTC).isoformat(),
            progress_percent=100,
            last_error=None,
            timeframe_ranges={
                tf: (rows[0].open_time.isoformat(), rows[-1].open_time.isoformat())
                for tf, rows in series.items()
            },
        )
        _atomic_json_write(manifest_path, _manifest_payload(manifest))
        progress_path = dataset_dir / "progress.json"
        _atomic_json_write(
            progress_path,
            {
                "symbol": symbol,
                "status": DatasetStatus.VERIFIED.value,
                "timeframe": None,
                "downloaded_candles": sum(tf_counts.values()),
                "expected_candles": sum(tf_counts.values()),
                "percent": 100,
                "updated_at": datetime.now(UTC).isoformat(),
                "error": None,
            },
        )
        return manifest

    def load_verified(self, symbol: str, timeframe: str) -> tuple[Candle, ...]:
        """Load candles only when the complete dataset manifest verifies."""

        if self.status(symbol) is not DatasetStatus.VERIFIED:
            raise RuntimeError(f"dataset for {symbol} is not verified")
        dataset_dir = self._storage_dir / "market" / symbol
        manifest = json.loads((dataset_dir / "manifest.json").read_text(encoding="utf-8"))
        if timeframe not in manifest.get("timeframe_checksums", {}):
            raise ValueError(f"timeframe {timeframe} is not present in the verified dataset")
        actual_start = _utc(datetime.fromisoformat(manifest["actual_start"]), name="actual_start")
        requested_end = _utc(
            datetime.fromisoformat(manifest["requested_end"]), name="requested_end"
        )
        path = dataset_dir / f"{timeframe}_{_range_name(actual_start, requested_end)}.json"
        return tuple(_read_candles(path))

    async def _download_timeframe(
        self,
        *,
        symbol: str,
        timeframe: str,
        actual_start: datetime,
        end: datetime,
        partial_path: Path,
        seed: list[Candle],
        duplicate_detected: bool,
        progress_path: Path,
        completed_before: int,
        total_expected: int,
    ) -> tuple[list[Candle], bool]:
        interval_ms = INTERVAL_MILLISECONDS[timeframe]
        end_ms = _to_ms(end)
        by_open = {item.open_time: item for item in seed}
        cursor = _to_ms(actual_start)
        # Resume only the contiguous prefix. If a prior run checkpointed a
        # sparse page, fetching restarts at its first missing interval rather
        # than incorrectly skipping the gap while retaining later rows.
        for item in sorted(by_open.values(), key=lambda row: row.open_time):
            if _to_ms(item.open_time) != cursor:
                break
            cursor += interval_ms
        while cursor < end_ms:
            page = await self._request_page(
                symbol=symbol,
                timeframe=timeframe,
                start_time_ms=cursor,
                end_time_ms=end_ms,
                now_ms=end_ms + interval_ms,
            )
            if not page:
                break
            page_seen: set[datetime] = set()
            max_open_ms: int | None = None
            for item in page:
                if item.open_time.tzinfo is None:
                    duplicate_detected = True
                    continue
                item_open_ms = _to_ms(item.open_time)
                max_open_ms = (
                    item_open_ms if max_open_ms is None else max(max_open_ms, item_open_ms)
                )
                if item.open_time in page_seen:
                    existing_page = by_open.get(item.open_time)
                    if existing_page is not None and _ohlcv_conflict(existing_page, item):
                        duplicate_detected = True
                    continue
                page_seen.add(item.open_time)
                if item.symbol != symbol or item.timeframe != timeframe:
                    duplicate_detected = True
                    continue
                # Binance can return the currently forming final row. It is
                # intentionally ignored and never reaches a partial/final file.
                if not item.closed or not (actual_start <= item.open_time < end):
                    continue
                existing = by_open.get(item.open_time)
                if existing is not None:
                    if _ohlcv_conflict(existing, item):
                        duplicate_detected = True
                    continue
                by_open[item.open_time] = item
            if max_open_ms is None or max_open_ms < cursor:
                raise RuntimeError(f"{timeframe} history pagination made no progress")
            values = sorted(by_open.values(), key=lambda item: item.open_time)
            _atomic_json_write(partial_path, [item.model_dump(mode="json") for item in values])
            downloaded = completed_before + len(values)
            await self._emit_progress(
                progress_path,
                symbol=symbol,
                status=DatasetStatus.DOWNLOADING,
                timeframe=timeframe,
                downloaded=downloaded,
                expected=total_expected,
            )
            next_cursor = max_open_ms + interval_ms
            if next_cursor <= cursor:
                raise RuntimeError(f"{timeframe} history pagination made no progress")
            cursor = next_cursor
        return sorted(by_open.values(), key=lambda item: item.open_time), duplicate_detected

    async def _request_page(
        self,
        *,
        symbol: str,
        timeframe: str,
        start_time_ms: int,
        end_time_ms: int,
        now_ms: int,
    ) -> list[Candle]:
        last_error: Exception | None = None
        for attempt in range(self._max_attempts):
            try:
                return await self._client.klines(
                    symbol=symbol,
                    interval=timeframe,
                    start_time_ms=start_time_ms,
                    end_time_ms=end_time_ms,
                    limit=1000,
                    now_ms=now_ms,
                )
            except Exception as exc:
                last_error = exc
                if attempt + 1 == self._max_attempts:
                    break
                delay = self._backoff_base_seconds * (2**attempt)
                if delay:
                    await self._sleep(delay)
        raise RuntimeError(f"{timeframe} history request failed after retries") from last_error

    def _load_existing(
        self,
        final_path: Path,
        partial_path: Path,
        *,
        symbol: str,
        timeframe: str,
    ) -> tuple[list[Candle], bool]:
        path = partial_path if partial_path.exists() else final_path
        if not path.exists():
            return [], False
        try:
            candles = _read_candles(path)
            duplicate = len({item.open_time for item in candles}) != len(candles)
            if any(item.symbol != symbol or item.timeframe != timeframe for item in candles):
                return [], False
            return candles, duplicate
        except (OSError, ValueError, TypeError, json.JSONDecodeError):
            # A torn or malformed checkpoint is safe to discard; it is not a
            # verified duplicate and should not poison the next retry.
            return [], False

    def _verify_series(
        self,
        candles: list[Candle],
        *,
        symbol: str,
        timeframe: str,
        actual_start: datetime,
        end: datetime,
        expected: int,
        duplicate_detected: bool,
    ) -> VerificationResult:
        base = verify_candles(candles, timeframe)
        if any(item.symbol != symbol for item in candles):
            return VerificationResult(False, base.missing_intervals, base.duplicate_intervals)
        if not candles or len(candles) != expected:
            missing = max(base.missing_intervals, max(expected - len(candles), 0))
            return VerificationResult(
                False,
                missing,
                base.duplicate_intervals + int(duplicate_detected),
            )
        interval_ms = INTERVAL_MILLISECONDS[timeframe]
        if _to_ms(candles[0].open_time) != _to_ms(actual_start):
            return VerificationResult(
                False,
                max(base.missing_intervals, 1),
                base.duplicate_intervals,
            )
        if _to_ms(candles[-1].open_time) + interval_ms != _to_ms(end):
            return VerificationResult(
                False,
                max(base.missing_intervals, 1),
                base.duplicate_intervals,
            )
        if any(_to_ms(item.close_time) >= _to_ms(end) for item in candles):
            return VerificationResult(False, base.missing_intervals, base.duplicate_intervals)
        if duplicate_detected:
            return VerificationResult(False, base.missing_intervals, base.duplicate_intervals + 1)
        return base

    def _is_verified_series(
        self,
        candles: list[Candle],
        *,
        symbol: str,
        timeframe: str,
        actual_start: datetime,
        end: datetime,
        expected: int,
        duplicate_detected: bool,
    ) -> bool:
        return self._verify_series(
            candles,
            symbol=symbol,
            timeframe=timeframe,
            actual_start=actual_start,
            end=end,
            expected=expected,
            duplicate_detected=duplicate_detected,
        ).verified

    @staticmethod
    def _expected_count(actual_start: datetime, end: datetime, timeframe: str) -> int:
        duration_ms = _to_ms(end) - _to_ms(actual_start)
        interval_ms = INTERVAL_MILLISECONDS[timeframe]
        if duration_ms <= 0 or duration_ms % interval_ms:
            return 0
        return duration_ms // interval_ms

    @staticmethod
    def _combined_checksum(checksums: dict[str, str]) -> str:
        # Keep the original manifest identity format stable for existing
        # datasets while including every timeframe in lexical order.
        value = "|".join(
            f"{timeframe}:{checksum}" for timeframe, checksum in sorted(checksums.items())
        )
        return hashlib.sha256(value.encode()).hexdigest()

    @staticmethod
    def _percent(downloaded: int, expected: int) -> int:
        if expected <= 0:
            return 0
        return min(99, int(downloaded * 100 / expected))

    async def _emit_progress(
        self,
        path: Path,
        *,
        symbol: str,
        status: DatasetStatus,
        timeframe: str | None,
        downloaded: int,
        expected: int,
        error: str | None = None,
    ) -> None:
        progress = DatasetProgress(
            symbol=symbol,
            status=status,
            timeframe=timeframe,
            downloaded_candles=downloaded,
            expected_candles=expected,
            percent=(
                100
                if status is DatasetStatus.VERIFIED
                else self._percent(downloaded, expected)
            ),
            updated_at=datetime.now(UTC).isoformat(),
            error=error,
        )
        await self._emit(progress, path)

    async def _emit(self, progress: DatasetProgress, path: Path) -> None:
        payload = asdict(progress)
        payload["status"] = progress.status.value
        _atomic_json_write(path, payload)
        callback = self._progress_callback
        if callback is None:
            return
        result = callback(progress)
        if inspect.isawaitable(result):
            await cast(Awaitable[object], result)


__all__ = ["DatasetProgress", "DatasetService"]
