"""Live market ingestion — the only writer of verified candles and quotes into the runtime.

Nothing here invents a price. When the exchange is unreachable the snapshot reports
``unavailable``/``degraded`` and the runtime stays blocked, which is what the preflight
gate and the dashboard show the operator.
"""

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import Callable
from contextlib import suppress
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Protocol

import httpx

from goldguard.config import Settings
from goldguard.domain.models import Candle, Quote
from goldguard.market.binance import BinancePublicClient, SymbolFilters
from goldguard.market.history import verify_candles
from goldguard.market.live_stream import (
    CHART_INTERVALS,
    MarketTickHub,
    run_binance_socket,
)
from goldguard.services.runtime import (
    TradingRuntime,
    is_runtime_error_recorded,
    mark_runtime_error_recorded,
)
from goldguard.storage.repositories import MarketCandleRepository

logger = logging.getLogger("goldguard.ingestion")

HISTORY_LIMIT = 300
QUOTE_STALE_SECONDS = 120.0
BUCKET_SECONDS = {"1m": 60, "5m": 300, "15m": 900, "1h": 3600, "4h": 14400, "1d": 86400}
RUNTIME_QUOTE_MIN_INTERVAL = 0.25


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
        include_open: bool = False,
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
        self._aux_close: dict[str, datetime] = {}
        self._aux_quotes: dict[str, Quote] = {}
        self._aux_bars: dict[str, Candle] = {}
        self._aux_enabled = True
        self._autonomous = None
        self._autonomous_owner = False
        self._owned_http_client: httpx.AsyncClient | None = None
        self._live_socket = client is None
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
        self._ws_task: asyncio.Task[None] | None = None
        self._runtime_tasks: set[asyncio.Task[object]] = set()
        self._ws_stop = asyncio.Event()
        self.hub = MarketTickHub()
        self._last_runtime_quote = 0.0

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
        if self._live_socket:
            self._ws_stop.clear()
            self._ws_task = asyncio.create_task(self._run_socket(), name="goldguard-market-ws")

    async def aclose(self) -> None:
        self._ws_stop.set()
        for task in (self._ws_task, self._task):
            if task is None:
                continue
            task.cancel()
            with suppress(asyncio.CancelledError, Exception):
                await task
        self._ws_task = None
        self._task = None
        runtime_tasks = tuple(self._runtime_tasks)
        for runtime_task in runtime_tasks:
            runtime_task.cancel()
        if runtime_tasks:
            await asyncio.gather(*runtime_tasks, return_exceptions=True)
        self._runtime_tasks.clear()
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

    def aux_quotes(self) -> dict[str, Quote]:
        return dict(self._aux_quotes)

    def aux_bars(self) -> dict[str, Candle]:
        return dict(self._aux_bars)

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
        if self._aux_enabled:
            await self._warmup_aux_symbols()
        if self._autonomous is not None:
            seeder = getattr(self._autonomous, "seed_history", None)
            if seeder is not None:
                seeder(
                    symbol,
                    list(self._candles.get("15m") or []),
                    list(self._candles.get("1h") or []),
                )

    async def _warmup_aux_symbols(self) -> None:
        for symbol in self._settings.paper_spot_symbols():
            if symbol == self._settings.symbol:
                continue
            try:
                bars_15m = await self._client.klines(
                    symbol=symbol, interval="15m", limit=HISTORY_LIMIT
                )
                bars_1h = await self._client.klines(
                    symbol=symbol, interval="1h", limit=HISTORY_LIMIT
                )
            except Exception as exc:
                logger.warning("aux warmup failed for %s: %s", symbol, exc)
                continue
            closed_15 = [item for item in bars_15m if item.closed]
            closed_1h = [item for item in bars_1h if item.closed]
            if closed_15:
                self._aux_close[symbol] = closed_15[-1].close_time
                self._aux_bars[symbol] = closed_15[-1]
            try:
                self._aux_quotes[symbol] = await self._client.quote(symbol)
            except Exception as exc:
                logger.warning("aux warmup quote failed for %s: %s", symbol, exc)
            self._runtime.seed_symbol_history(symbol, closed_15, closed_1h)
            if self._autonomous is not None:
                seeder = getattr(self._autonomous, "seed_history", None)
                if seeder is not None:
                    seeder(symbol, closed_15, closed_1h)

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
        if self.hub.latest_quote is None:
            self.hub.publish_quote(quote, force=True)
        self._source = "binance-ws" if self.hub.latest_quote is not None else "binance-rest"
        self._detail = None
        self._failures = 0
        self._refresh_verification()
        self._publish()

        if closed_entry_candle is not None:
            await self._dispatch_closed(closed_entry_candle, quote)
        await self._dispatch_quote(quote)
        await self._tick_aux_symbols()

    def set_aux_enabled(self, enabled: bool) -> None:
        self._aux_enabled = enabled

    def set_autonomous(self, runtime: object | None, *, owner: bool) -> None:
        self._autonomous = runtime
        self._autonomous_owner = owner and runtime is not None
        self._aux_enabled = self._autonomous_owner

    async def _dispatch_closed(self, candle: Candle, quote: Quote) -> None:
        if self._autonomous_owner and self._autonomous is not None:
            on_closed = getattr(self._autonomous, "on_closed_candle", None)
            if on_closed is not None:
                await on_closed(candle, quote)
            return
        await asyncio.to_thread(self._runtime.process_closed_candle, candle, quote)

    async def _dispatch_quote(self, quote: Quote, symbol: str | None = None) -> None:
        if self._autonomous_owner and self._autonomous is not None:
            on_quote = getattr(self._autonomous, "on_quote", None)
            if on_quote is not None:
                await on_quote(quote, symbol=symbol or self._settings.symbol)
            return
        await asyncio.to_thread(self._runtime.process_quote, quote)

    async def _tick_aux_symbols(self) -> None:
        if not self._aux_enabled:
            return
        for symbol in self._settings.paper_spot_symbols():
            if symbol == self._settings.symbol:
                continue
            try:
                quote = await self._client.quote(symbol)
                self._aux_quotes[symbol] = quote
                fetched = await self._client.klines(symbol=symbol, interval="15m", limit=4)
            except Exception as exc:
                logger.warning("aux spot tick failed for %s: %s", symbol, exc)
                continue
            closed = [item for item in fetched if item.closed]
            if not closed:
                continue
            last = closed[-1]
            self._aux_bars[symbol] = last
            previous = self._aux_close.get(symbol)
            if previous is not None and last.close_time <= previous:
                continue
            self._aux_close[symbol] = last.close_time
            await self._dispatch_closed(last, quote)

    async def _run_socket(self) -> None:
        await run_binance_socket(
            rest_base_url=self._settings.market_base_url,
            symbol=self._settings.symbol,
            on_quote=self._on_live_quote,
            on_kline=self._on_live_kline,
            stop=self._ws_stop,
        )

    def _on_live_quote(self, quote: Quote) -> None:
        self._latest_quote = quote
        self._source = "binance-ws"
        self._detail = None
        self.hub.publish_quote(quote)
        now = time.monotonic()
        if now - self._last_runtime_quote < RUNTIME_QUOTE_MIN_INTERVAL:
            return
        self._last_runtime_quote = now
        self._publish()
        if self._autonomous_owner:
            task = asyncio.create_task(self._dispatch_quote(quote), name="goldguard-ws-quote")
            self._runtime_tasks.add(task)
            task.add_done_callback(self._runtime_work_done)
            return
        self._spawn_runtime_work(
            lambda: self._runtime.process_quote(quote),
            "goldguard-ws-quote",
        )

    def _on_live_kline(self, candle: Candle) -> None:
        self.hub.publish_kline(candle)
        if not candle.closed:
            return
        if candle.timeframe in ("15m", "1h"):
            appended = self._merge(candle.timeframe, [candle])
            if appended and candle.timeframe == self._settings.entry_timeframe:
                quote = self._latest_quote
                if quote is not None:
                    if self._autonomous_owner:
                        task = asyncio.create_task(
                            self._dispatch_closed(appended[-1], quote),
                            name="goldguard-ws-close",
                        )
                        self._runtime_tasks.add(task)
                        task.add_done_callback(self._runtime_work_done)
                    else:
                        self._spawn_runtime_work(
                            lambda: self._runtime.process_closed_candle(appended[-1], quote),
                            "goldguard-ws-close",
                        )
            self._refresh_verification()
            self._publish()

    async def chart_candles(
        self, interval: str, limit: int, symbol: str | None = None
    ) -> list[Candle]:
        """Closed history plus the forming bar for the chart. Not used by the strategy."""
        if interval not in CHART_INTERVALS:
            raise ValueError(f"unsupported chart interval {interval}")
        limit = max(1, min(limit, 500))
        target = (symbol or self._settings.symbol).upper()
        same_book = target == self._settings.symbol
        if same_book and interval in ("15m", "1h") and self._candles.get(interval):
            closed = list(self._candles[interval][-limit:])
        else:
            closed = await self._client.klines(
                symbol=target,
                interval=interval,
                limit=limit,
                include_open=True,
            )
        if not same_book:
            return closed[-limit:]
        forming = self.hub.forming.get(interval)
        if forming is None:
            return closed
        if closed and closed[-1].open_time == forming.open_time:
            return [*closed[:-1], forming]
        if forming.closed:
            return closed
        return [*closed, forming]

    async def public_quote(self, symbol: str) -> Quote:
        return await self._client.quote(symbol.upper())

    def _spawn_runtime_work(self, operation: Callable[[], object], name: str) -> None:
        task = asyncio.create_task(asyncio.to_thread(operation), name=name)
        self._runtime_tasks.add(task)
        task.add_done_callback(self._runtime_work_done)

    def _runtime_work_done(self, task: asyncio.Task[object]) -> None:
        self._runtime_tasks.discard(task)
        if task.cancelled():
            return
        error = task.exception()
        if isinstance(error, Exception):
            self._record_failure(error)


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
        if not is_runtime_error_recorded(exc):
            self._runtime.record_runtime_error(str(exc))
            mark_runtime_error_recorded(exc)
        logger.warning("Market ingestion tick failed (%s): %s", self._failures, exc)

    @staticmethod
    def _bucket(timeframe: str, when: datetime) -> int:
        return int(when.timestamp()) // BUCKET_SECONDS[timeframe]
