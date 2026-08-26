import json
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

import httpx
import pytest
from goldguard.market.binance import BinancePublicClient, SymbolFilters


@pytest.mark.asyncio
async def test_klines_normalize_decimals_and_exclude_forming_candle() -> None:
    fixture_path = Path(__file__).parents[1] / "fixtures" / "binance_klines.json"
    payload = json.loads(fixture_path.read_text(encoding="utf-8"))

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/api/v3/klines"
        assert request.url.params["symbol"] == "PAXGUSDT"
        assert request.url.params["interval"] == "15m"
        return httpx.Response(200, json=payload)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http_client:
        client = BinancePublicClient(http_client=http_client, base_url="https://binance.test")
        candles = await client.klines(
            symbol="PAXGUSDT",
            interval="15m",
            now_ms=1787704000000,
        )

    assert len(candles) == 1
    assert candles[0].open == Decimal("2500.00")
    assert candles[0].close == Decimal("2506.00")
    assert candles[0].closed is True
    assert candles[0].open_time == datetime.fromtimestamp(1787702400, tz=UTC)


@pytest.mark.asyncio
async def test_exchange_filters_and_quote_are_typed() -> None:
    exchange_info = {
        "symbols": [
            {
                "symbol": "PAXGUSDT",
                "status": "TRADING",
                "isSpotTradingAllowed": True,
                "filters": [
                    {"filterType": "PRICE_FILTER", "tickSize": "0.01000000"},
                    {
                        "filterType": "LOT_SIZE",
                        "minQty": "0.00010000",
                        "maxQty": "100.00000000",
                        "stepSize": "0.00010000",
                    },
                    {"filterType": "NOTIONAL", "minNotional": "5.00000000"},
                ],
            }
        ]
    }

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/v3/exchangeInfo":
            return httpx.Response(200, json=exchange_info)
        if request.url.path == "/api/v3/ticker/bookTicker":
            return httpx.Response(200, json={"bidPrice": "2500.10", "askPrice": "2500.30"})
        raise AssertionError(f"unexpected request {request.url.path}")

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http_client:
        client = BinancePublicClient(http_client=http_client, base_url="https://binance.test")
        filters = await client.symbol_filters("PAXGUSDT")
        quote = await client.quote("PAXGUSDT", observed_at=datetime(2026, 8, 26, tzinfo=UTC))

    assert filters == SymbolFilters(
        tick_size=Decimal("0.01000000"),
        step_size=Decimal("0.00010000"),
        minimum_quantity=Decimal("0.00010000"),
        maximum_quantity=Decimal("100.00000000"),
        minimum_notional=Decimal("5.00000000"),
    )
    assert quote.bid == Decimal("2500.10")
    assert quote.ask == Decimal("2500.30")


@pytest.mark.asyncio
async def test_non_trading_symbol_is_rejected() -> None:
    payload = {
        "symbols": [
            {
                "symbol": "PAXGUSDT",
                "status": "BREAK",
                "isSpotTradingAllowed": True,
                "filters": [],
            }
        ]
    }

    async with httpx.AsyncClient(
        transport=httpx.MockTransport(lambda _: httpx.Response(200, json=payload))
    ) as http_client:
        client = BinancePublicClient(http_client=http_client, base_url="https://binance.test")
        with pytest.raises(RuntimeError, match="not available for spot trading"):
            await client.symbol_filters("PAXGUSDT")
