import asyncio
import random
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

import httpx

from goldguard.domain.models import Candle, Quote


@dataclass(frozen=True)
class SymbolFilters:
    tick_size: Decimal
    step_size: Decimal
    minimum_quantity: Decimal
    maximum_quantity: Decimal
    minimum_notional: Decimal


class BinancePublicClient:
    def __init__(
        self,
        *,
        http_client: httpx.AsyncClient,
        base_url: str = "https://api.binance.com",
        maximum_attempts: int = 3,
    ) -> None:
        self.http_client = http_client
        self.base_url = base_url.rstrip("/")
        self.maximum_attempts = maximum_attempts

    async def _get_json(self, path: str, params: dict[str, Any] | None = None) -> Any:
        last_error: Exception | None = None
        for attempt in range(self.maximum_attempts):
            try:
                response = await self.http_client.get(
                    f"{self.base_url}{path}",
                    params=params,
                    timeout=10,
                )
                response.raise_for_status()
                return response.json()
            except (httpx.TimeoutException, httpx.NetworkError, httpx.HTTPStatusError) as exc:
                last_error = exc
                retryable = not isinstance(exc, httpx.HTTPStatusError) or (
                    exc.response.status_code == 429 or exc.response.status_code >= 500
                )
                if not retryable or attempt + 1 == self.maximum_attempts:
                    break
                await asyncio.sleep((0.15 * (2**attempt)) + random.uniform(0, 0.05))
        raise RuntimeError(f"Binance public request failed for {path}") from last_error

    async def ping(self) -> bool:
        payload = await self._get_json("/api/v3/ping")
        return bool(payload == {})

    async def server_time_ms(self) -> int:
        payload = await self._get_json("/api/v3/time")
        if not isinstance(payload, dict) or not isinstance(payload.get("serverTime"), int):
            raise RuntimeError("Binance server-time response was malformed")
        return int(payload["serverTime"])

    async def system_is_normal(self) -> bool:
        payload = await self._get_json("/sapi/v1/system/status")
        return isinstance(payload, dict) and payload.get("status") == 0

    async def symbol_filters(self, symbol: str) -> SymbolFilters:
        payload = await self._get_json("/api/v3/exchangeInfo", {"symbol": symbol})
        symbols = payload.get("symbols", []) if isinstance(payload, dict) else []
        match = next((item for item in symbols if item.get("symbol") == symbol), None)
        if (
            match is None
            or match.get("status") != "TRADING"
            or match.get("isSpotTradingAllowed") is not True
        ):
            raise RuntimeError(f"{symbol} is not available for spot trading")
        by_type = {item.get("filterType"): item for item in match.get("filters", [])}
        try:
            price = by_type["PRICE_FILTER"]
            lot = by_type["LOT_SIZE"]
            notional = by_type.get("NOTIONAL") or by_type["MIN_NOTIONAL"]
            return SymbolFilters(
                tick_size=Decimal(str(price["tickSize"])),
                step_size=Decimal(str(lot["stepSize"])),
                minimum_quantity=Decimal(str(lot["minQty"])),
                maximum_quantity=Decimal(str(lot["maxQty"])),
                minimum_notional=Decimal(str(notional["minNotional"])),
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise RuntimeError(f"{symbol} exchange filters were malformed") from exc

    async def quote(self, symbol: str, *, observed_at: datetime | None = None) -> Quote:
        payload = await self._get_json("/api/v3/ticker/bookTicker", {"symbol": symbol})
        try:
            return Quote(
                bid=Decimal(str(payload["bidPrice"])),
                ask=Decimal(str(payload["askPrice"])),
                observed_at=observed_at or datetime.now(UTC),
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise RuntimeError(f"{symbol} quote response was malformed") from exc

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
    ) -> list[Candle]:
        params: dict[str, Any] = {"symbol": symbol, "interval": interval, "limit": limit}
        if start_time_ms is not None:
            params["startTime"] = start_time_ms
        if end_time_ms is not None:
            params["endTime"] = end_time_ms
        payload = await self._get_json("/api/v3/klines", params)
        current_ms = now_ms if now_ms is not None else int(time.time() * 1000)
        candles: list[Candle] = []
        if not isinstance(payload, list):
            raise RuntimeError("Binance kline response was malformed")
        for raw in payload:
            if not isinstance(raw, list) or len(raw) < 7:
                raise RuntimeError("Binance kline row was malformed")
            close_ms = int(raw[6])
            forming = close_ms >= current_ms
            if forming and not include_open:
                continue
            candles.append(
                Candle(
                    symbol=symbol,
                    timeframe=interval,
                    open_time=datetime.fromtimestamp(int(raw[0]) / 1000, tz=UTC),
                    close_time=datetime.fromtimestamp(close_ms / 1000, tz=UTC),
                    open=Decimal(str(raw[1])),
                    high=Decimal(str(raw[2])),
                    low=Decimal(str(raw[3])),
                    close=Decimal(str(raw[4])),
                    volume=Decimal(str(raw[5])),
                    closed=not forming,
                )
            )
        return candles
