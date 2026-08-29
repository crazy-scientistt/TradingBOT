"""Binance WebSocket ticks for charts and live quotes.

Public market data — no API key. Strategy still only acts on *closed* 15m candles.
This module never invents a price: it forwards exchange bookTicker / kline payloads.
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from collections.abc import Callable
from contextlib import suppress
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from goldguard.domain.models import Candle, Quote

logger = logging.getLogger("goldguard.market.stream")

CHART_INTERVALS = ("1m", "5m", "15m", "1h", "4h", "1d")
QUOTE_SSE_MIN_INTERVAL = 0.25


def stream_base_url(rest_base_url: str) -> str:
    rest = rest_base_url.rstrip("/")
    if "data-api.binance.vision" in rest:
        return "wss://data-stream.binance.vision"
    return "wss://stream.binance.com:9443"


def combined_stream_url(rest_base_url: str, symbol: str) -> str:
    stream_id = symbol.lower()
    parts = [f"{stream_id}@bookTicker"]
    parts.extend(f"{stream_id}@kline_{interval}" for interval in CHART_INTERVALS)
    return f"{stream_base_url(rest_base_url)}/stream?streams={'/'.join(parts)}"


def parse_book_ticker(
    payload: dict[str, Any],
    *,
    observed_at: datetime | None = None,
) -> Quote | None:
    data = payload.get("data") if "data" in payload else payload
    if not isinstance(data, dict):
        return None
    try:
        bid = Decimal(str(data["b"]))
        ask = Decimal(str(data["a"]))
    except (KeyError, TypeError, ValueError):
        return None
    if bid <= 0 or ask <= 0 or ask < bid:
        return None
    return Quote(bid=bid, ask=ask, observed_at=observed_at or datetime.now(UTC))


def parse_kline(payload: dict[str, Any], *, symbol: str) -> Candle | None:
    data = payload.get("data") if "data" in payload else payload
    if not isinstance(data, dict):
        return None
    kline = data.get("k")
    if not isinstance(kline, dict):
        return None
    try:
        open_ms = int(kline["t"])
        close_ms = int(kline["T"])
        interval = str(kline["i"])
        candle = Candle(
            symbol=symbol,
            timeframe=interval,
            open_time=datetime.fromtimestamp(open_ms / 1000, tz=UTC),
            close_time=datetime.fromtimestamp(close_ms / 1000, tz=UTC),
            open=Decimal(str(kline["o"])),
            high=Decimal(str(kline["h"])),
            low=Decimal(str(kline["l"])),
            close=Decimal(str(kline["c"])),
            volume=Decimal(str(kline["v"])),
            closed=bool(kline.get("x")),
        )
    except (KeyError, TypeError, ValueError):
        return None
    return candle


def candle_payload(candle: Candle) -> dict[str, Any]:
    return {
        "symbol": candle.symbol,
        "interval": candle.timeframe,
        "openTime": candle.open_time.isoformat(),
        "closeTime": candle.close_time.isoformat(),
        "fullTime": candle.close_time.isoformat(),
        "time": candle.close_time.strftime("%H:%M"),
        "open": float(candle.open),
        "high": float(candle.high),
        "low": float(candle.low),
        "close": float(candle.close),
        "volume": float(candle.volume),
        "closed": candle.closed,
    }


def quote_payload(quote: Quote) -> dict[str, Any]:
    spread = quote.ask - quote.bid
    mid = (quote.ask + quote.bid) / Decimal("2")
    return {
        "bid": float(quote.bid),
        "ask": float(quote.ask),
        "spread": float(spread),
        "spread_rate": float(spread / mid) if mid else 0.0,
        "observed_at": quote.observed_at.isoformat(),
    }


class MarketTickHub:
    """In-process fan-out for SSE subscribers. Latest quote / forming bars are cached."""

    def __init__(self) -> None:
        self._queues: set[asyncio.Queue[dict[str, Any]]] = set()
        self.latest_quote: Quote | None = None
        self.forming: dict[str, Candle] = {}
        self.source = "binance-ws"
        self._last_quote_push = 0.0

    def snapshot(self) -> dict[str, Any]:
        return {
            "quote": quote_payload(self.latest_quote) if self.latest_quote else None,
            "forming": {
                interval: candle_payload(candle) for interval, candle in self.forming.items()
            },
            "source": self.source,
        }

    def subscribe(self) -> asyncio.Queue[dict[str, Any]]:
        queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue(maxsize=64)
        self._queues.add(queue)
        return queue

    def unsubscribe(self, queue: asyncio.Queue[dict[str, Any]]) -> None:
        self._queues.discard(queue)

    def publish_quote(self, quote: Quote, *, force: bool = False) -> None:
        self.latest_quote = quote
        now = time.monotonic()
        if not force and now - self._last_quote_push < QUOTE_SSE_MIN_INTERVAL:
            return
        self._last_quote_push = now
        self._broadcast({"type": "quote", **quote_payload(quote)})

    def publish_kline(self, candle: Candle) -> None:
        self.forming[candle.timeframe] = candle
        if candle.closed:
            # Forming slot is replaced by the next open bar; keep last closed visible until then.
            pass
        self._broadcast({"type": "kline", "interval": candle.timeframe, **candle_payload(candle)})

    def _broadcast(self, event: dict[str, Any]) -> None:
        stale: list[asyncio.Queue[dict[str, Any]]] = []
        for queue in self._queues:
            try:
                queue.put_nowait(event)
            except asyncio.QueueFull:
                stale.append(queue)
        for queue in stale:
            self._queues.discard(queue)


async def run_binance_socket(
    *,
    rest_base_url: str,
    symbol: str,
    on_quote: Callable[[Quote], None],
    on_kline: Callable[[Candle], None],
    stop: asyncio.Event,
) -> None:
    """Reconnect loop. REST ingestion remains the fallback if this exits."""
    try:
        import websockets
    except ImportError:  # pragma: no cover - runtime extra
        logger.warning("websockets package missing; live chart stream disabled")
        return

    url = combined_stream_url(rest_base_url, symbol)
    backoff = 1.0
    while not stop.is_set():
        try:
            logger.info("Connecting Binance live stream %s", url)
            async with websockets.connect(
                url,
                ping_interval=20,
                ping_timeout=20,
                max_size=2**20,
            ) as ws:
                backoff = 1.0
                while not stop.is_set():
                    raw = await asyncio.wait_for(ws.recv(), timeout=30)
                    if isinstance(raw, bytes):
                        raw = raw.decode("utf-8")
                    try:
                        payload = json.loads(raw)
                    except json.JSONDecodeError:
                        continue
                    if not isinstance(payload, dict):
                        continue
                    stream = str(payload.get("stream") or "")
                    if stream.endswith("@bookTicker") or "b" in (payload.get("data") or {}):
                        quote = parse_book_ticker(payload)
                        if quote is not None:
                            on_quote(quote)
                    has_kline = isinstance(payload.get("data"), dict) and "k" in payload["data"]
                    if "@kline_" in stream or has_kline:
                        candle = parse_kline(payload, symbol=symbol)
                        if candle is not None:
                            on_kline(candle)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.warning("Binance live stream dropped (%s); retry in %.1ss", exc, backoff)
            with suppress(TimeoutError):
                await asyncio.wait_for(stop.wait(), timeout=backoff)
            backoff = min(backoff * 2, 30.0)
