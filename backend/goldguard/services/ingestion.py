"""Live market ingestion — the only writer of verified candles and quotes into the runtime.

Nothing here invents a price. When the exchange is unreachable the snapshot reports
``unavailable``/``degraded`` and the runtime stays blocked, which is what the preflight
gate and the dashboard show the operator.
"""

from __future__ import annotations

import asyncio
import logging
from contextlib import suppress
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Protocol

import httpx

from goldguard.config import Settings
from goldguard.domain.models import Candle, Quote
from goldguard.market.binance import BinancePublicClient, SymbolFilters
from goldguard.market.history import verify_candles
from goldguard.services.runtime import TradingRuntime
from goldguard.storage.repositories import MarketCandleRepository

logger = logging.getLogger("goldguard.ingestion")

HISTORY_LIMIT = 300
QUOTE_STALE_SECONDS = 120.0
BUCKET_SECONDS = {"15m": 900, "1h": 3600}


class MarketClient(Protocol):
    async def symbol_filters(self, symbol: str) -> SymbolFilters: ...

    async def quote(self, symbol: str, *, observed_at: datetime | None = None) -> Quote: ...

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


@dataclass(frozen=True)
class MarketSnapshot:
    availability: str
    source: str
    observed_at: datetime | None
    stale: bool
    detail: str | None
    verified: bool
    candles_15m: tuple[Candle, ...]
    candles_1h: tuple[Candle, ...]
    latest_quote: Quote | None
    filters: SymbolFilters | None


class MarketIngestionService:
    def __init__(
        self,
        *,
        settings: Settings,
        runtime: TradingRuntime,
        candle_repo: MarketCandleRepository,
        client: MarketClient | None = None,
        poll_seconds: float = 10.0,
    ) -> None:
        self._settings = settings
        self._runtime = runtime
        self._candle_repo = candle_repo
        self._poll_seconds = poll_seconds
        self._owned_http_client: httpx.AsyncClient | None = None
        if client is None:
            self._owned_http_client = httpx.AsyncClient()
            client = BinancePublicClient(
                http_client=self._owned_http_client,
                base_url=settings.market_base_url,
            )
        self._client = client

        self._candles: dict[str, list[Candle]] = {"15m": [], "1h": []}
        self._buckets: dict[str, int] = {}
        self._filters: SymbolFilters | None = None
        self._latest_quote: Quote | None = None
        self._verified = False
        self._source = "unconfigured"
        self._detail: str | None = "market ingestion has not run yet"
        self._failures = 0
        self._task: asyncio.Task[None] | None = None

    # -- lifecycle ----------------------------------------------------------------

    async def start(self) -> None:
        self._load_persisted()
        if not self._settings.market_ingestion_enabled:
            self._detail = "market ingestion disabled by configuration"
            self._publish()
            return
        try:
            await self._warmup()
        except Exception as exc:  # pragma: no cover - network dependent
            self._record_failure(exc)
        self._task = asyncio.create_task(self._run(), name="goldguard-market-ingestion")

    async def aclose(self) -> None:
        if self._task is not None:
            self._task.cancel()
            with suppress(asyncio.CancelledError, Exception):
                await self._task
            self._task = None
        if self._owned_http_client is not None:
            await self._owned_http_client.aclose()
            self._owned_http_client = None

    # -- reads --------------------------------------------------------------------

    def snapshot(self) -> MarketSnapshot:
        quote = self._latest_quote
        candles = self._candles["15m"]
        observed_at = quote.observed_at if quote else (candles[-1].close_time if candles else None)
        stale = observed_at is None or (
            (datetime.now(UTC) - observed_at).total_seconds() > QUOTE_STALE_SECONDS
        )
        if quote is None and not candles:
            availability = "unavailable"
        elif self._verified and quote is not None and not stale:
            availability = "available"
        else:
            availability = "degraded"
        return MarketSnapshot(
            availability=availability,
            source=self._source,
            observed_at=observed_at,
            stale=stale,
            detail=self._detail,
            verified=self._verified,
            candles_15m=tuple(candles),
            candles_1h=tuple(self._candles["1h"]),
            latest_quote=quote,
            filters=self._filters,
        )

    # -- internals ----------------------------------------------------------------

    def _load_persisted(self) -> None:
        loaded = False
        for timeframe in ("15m", "1h"):
            stored = self._candle_repo.load_candles(
                self._settings.symbol, timeframe, limit=HISTORY_LIMIT
            )
            if stored:
                self._candles[timeframe] = stored
                loaded = True
        if loaded:
            self._source = "sqlite-market-candles"
            self._detail = "replayed persisted candles; awaiting live quote"
            self._refresh_verification()
            self._publish()

    async def _warmup(self) -> None:
        symbol = self._settings.symbol
        self._filters = await self._client.symbol_filters(symbol)
        for timeframe in ("15m", "1h"):
            fetched = await self._client.klines(
                symbol=symbol, interval=timeframe, limit=HISTORY_LIMIT
            )
            self._merge(timeframe, fetched)
            self._buckets[timeframe] = self._bucket(timeframe, datetime.now(UTC))
        self._latest_quote = await self._client.quote(symbol)
        self._source = "binance-rest"
        self._detail = None
        self._failures = 0
        self._refresh_verification()
        self._publish()

    async def _run(self) -> None:
        while True:
            delay = self._poll_seconds
            try:
                await self._tick()
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                self._record_failure(exc)
                delay = min(self._poll_seconds * (2 ** min(self._failures, 4)), 120.0)
            await asyncio.sleep(delay)

    async def _tick(self) -> None:
        symbol = self._settings.symbol
        now = datetime.now(UTC)
        if self._filters is None:
            self._filters = await self._client.symbol_filters(symbol)
        quote = await self._client.quote(symbol, observed_at=now)

        closed_entry_candle: Candle | None = None
        for timeframe in ("1h", "15m"):
            if self._bucket(timeframe, now) == self._buckets.get(timeframe):
                continue
            # limit=3 covers a single missed poll without re-downloading history.
            fetched = await self._client.klines(symbol=symbol, interval=timeframe, limit=3)
            appended = self._merge(timeframe, fetched)
            self._buckets[timeframe] = self._bucket(timeframe, now)
            if appended and timeframe == self._settings.entry_timeframe:
                closed_entry_candle = appended[-1]

        self._latest_quote = quote
        self._source = "binance-rest"
        self._detail = None
        self._failures = 0
        self._refresh_verification()
        self._publish()

        if closed_entry_candle is not None:
            await asyncio.to_thread(self._runtime.process_closed_candle, closed_entry_candle, quote)
        await asyncio.to_thread(self._runtime.process_quote, quote)

    def _merge(self, timeframe: str, fetched: list[Candle]) -> list[Candle]:
        """Store newly closed candles and return the ones this call added, oldest first."""
        existing = self._candles[timeframe]
        known = {candle.open_time for candle in existing}
        appended = [candle for candle in fetched if candle.closed and candle.open_time not in known]
        if not appended:
            return []
        appended.sort(key=lambda candle: candle.open_time)
        self._candle_repo.upsert_candles(appended, source="binance-rest")
        merged = existing + appended
        merged.sort(key=lambda candle: candle.open_time)
        self._candles[timeframe] = merged[-HISTORY_LIMIT:]
        return appended

    def _refresh_verification(self) -> None:
        was_verified = self._verified
        results = {
            timeframe: verify_candles(self._candles[timeframe], timeframe)
            for timeframe in ("15m", "1h")
        }
        self._verified = all(result.verified for result in results.values())
        if self._verified or not was_verified:
            return
        for timeframe, result in results.items():
            if result.verified:
                continue
            self._candle_repo.record_quality_event(
                symbol=self._settings.symbol,
                timeframe=timeframe,
                event_type="CANDLE_SERIES_UNVERIFIED",
                details={
                    "missing_intervals": result.missing_intervals,
                    "duplicate_intervals": result.duplicate_intervals,
                    "candle_count": len(self._candles[timeframe]),
                },
            )
        self._detail = "candle history failed contiguity verification"

    def _publish(self) -> None:
        self._runtime.configure_market_inputs(
            source=self._source,
            verified=self._verified,
            filters=self._filters,
            candles_15m=list(self._candles["15m"]),
            candles_1h=list(self._candles["1h"]),
            latest_quote=self._latest_quote,
        )

    def _record_failure(self, exc: Exception) -> None:
        self._failures += 1
        self._detail = f"market request failed: {exc}"
        record_error = getattr(self._runtime, "record_runtime_error", None)
        if callable(record_error):
            record_error(str(exc))
        logger.warning("Market ingestion tick failed (%s): %s", self._failures, exc)

    @staticmethod
    def _bucket(timeframe: str, when: datetime) -> int:
        return int(when.timestamp()) // BUCKET_SECONDS[timeframe]
