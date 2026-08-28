from datetime import UTC, datetime
from decimal import Decimal

from goldguard.market.live_stream import (
    combined_stream_url,
    parse_book_ticker,
    parse_kline,
    stream_base_url,
)


def test_vision_rest_maps_to_vision_websocket() -> None:
    assert stream_base_url("https://data-api.binance.vision") == "wss://data-stream.binance.vision"
    url = combined_stream_url("https://data-api.binance.vision", "PAXGUSDT")
    assert url.startswith("wss://data-stream.binance.vision/stream?streams=")
    assert "paxgusdt@bookTicker" in url
    assert "paxgusdt@kline_15m" in url


def test_parse_book_ticker() -> None:
    quote = parse_book_ticker(
        {"stream": "paxgusdt@bookTicker", "data": {"b": "4599.30", "a": "4599.31"}},
        observed_at=datetime(2026, 8, 28, 12, 0, tzinfo=UTC),
    )
    assert quote is not None
    assert quote.bid == Decimal("4599.30")
    assert quote.ask == Decimal("4599.31")


def test_parse_forming_and_closed_kline() -> None:
    raw = {
        "stream": "paxgusdt@kline_15m",
        "data": {
            "k": {
                "t": 1_788_761_700_000,
                "T": 1_788_762_599_999,
                "i": "15m",
                "o": "4599.00",
                "h": "4601.00",
                "l": "4598.00",
                "c": "4600.50",
                "v": "12.4",
                "x": False,
            }
        },
    }
    forming = parse_kline(raw, symbol="PAXGUSDT")
    assert forming is not None
    assert forming.closed is False
    assert forming.close == Decimal("4600.50")

    raw["data"]["k"]["x"] = True
    closed = parse_kline(raw, symbol="PAXGUSDT")
    assert closed is not None
    assert closed.closed is True


def test_garbage_payloads_are_ignored() -> None:
    assert parse_book_ticker({"data": {"b": "0", "a": "1"}}) is None
    assert parse_kline({"data": {"k": {}}}, symbol="PAXGUSDT") is None
