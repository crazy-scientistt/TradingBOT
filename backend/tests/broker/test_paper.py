from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from goldguard.broker.paper import PaperBroker, PaperOrderRejected
from goldguard.domain.enums import ExitReason, OrderSide
from goldguard.domain.models import Candle, Quote, TradePlan

NOW = datetime(2026, 8, 26, 12, tzinfo=UTC)


def plan() -> TradePlan:
    return TradePlan(
        entry=Decimal("2500"),
        stop=Decimal("2487.50"),
        target=Decimal("2525"),
        quantity=Decimal("0.02"),
        risk_amount=Decimal("0.25"),
        expected_fees=Decimal("0.10"),
    )


def quote(bid: str, ask: str) -> Quote:
    return Quote(bid=Decimal(bid), ask=Decimal(ask), observed_at=NOW)


def test_market_entry_uses_ask_plus_slippage_and_preserves_cash() -> None:
    broker = PaperBroker(
        starting_cash=Decimal("100"),
        fee_rate=Decimal("0.001"),
        slippage_rate=Decimal("0.0002"),
    )

    fill = broker.open_long(plan(), quote("2499.80", "2500"), client_order_id="entry-1")

    assert fill.side is OrderSide.BUY
    assert fill.price == Decimal("2500.5000")
    assert fill.fee == Decimal("0.050010000")
    assert broker.cash == Decimal("49.939990000")
    assert broker.position is not None
    assert broker.equity(quote("2510", "2510.20")) == Decimal("100.139990000")


def test_market_exit_uses_bid_minus_slippage_and_realizes_net_pnl() -> None:
    broker = PaperBroker(Decimal("100"), Decimal("0.001"), Decimal("0.0002"))
    broker.open_long(plan(), quote("2499.80", "2500"), client_order_id="entry-1")

    trade = broker.exit_long(
        quote("2525", "2525.20"),
        client_order_id="exit-1",
        reason=ExitReason.TAKE_PROFIT,
    )

    assert trade.exit_fill.price == Decimal("2524.4950")
    assert trade.realized_pnl == Decimal("0.379400100")
    assert broker.cash == Decimal("100.379400100")
    assert broker.position is None


def test_duplicate_client_order_id_is_idempotent() -> None:
    broker = PaperBroker(Decimal("100"), Decimal("0.001"), Decimal("0.0002"))

    first = broker.open_long(plan(), quote("2499.80", "2500"), client_order_id="entry-1")
    second = broker.open_long(plan(), quote("2499.80", "2500"), client_order_id="entry-1")

    assert first is second
    assert broker.cash == Decimal("49.939990000")
    assert len(broker.fills) == 1


def test_existing_position_rejects_averaging_down() -> None:
    broker = PaperBroker(Decimal("100"), Decimal("0.001"), Decimal("0.0002"))
    broker.open_long(plan(), quote("2499.80", "2500"), client_order_id="entry-1")

    with pytest.raises(PaperOrderRejected, match="position already open"):
        broker.open_long(plan(), quote("2480", "2480.20"), client_order_id="entry-2")


def test_insufficient_cash_rejects_without_partial_fill() -> None:
    broker = PaperBroker(Decimal("10"), Decimal("0.001"), Decimal("0.0002"))

    with pytest.raises(PaperOrderRejected, match="insufficient paper cash"):
        broker.open_long(plan(), quote("2499.80", "2500"), client_order_id="entry-1")

    assert broker.cash == Decimal("10")
    assert broker.position is None
    assert broker.fills == ()


def test_same_candle_stop_and_target_assumes_stop_first() -> None:
    broker = PaperBroker(Decimal("100"), Decimal("0.001"), Decimal("0.0002"))
    broker.open_long(plan(), quote("2499.80", "2500"), client_order_id="entry-1")
    candle = Candle(
        symbol="PAXGUSDT",
        timeframe="15m",
        open_time=NOW,
        close_time=NOW + timedelta(minutes=15),
        open=Decimal("2501"),
        high=Decimal("2530"),
        low=Decimal("2480"),
        close=Decimal("2520"),
        volume=Decimal("10"),
        closed=True,
    )

    trade = broker.process_candle(candle, client_order_id="exit-1")

    assert trade is not None
    assert trade.exit_reason is ExitReason.STOP_LOSS
    assert trade.exit_fill.price == Decimal("2487.002500")


def test_gap_through_stop_fills_at_first_available_price() -> None:
    broker = PaperBroker(Decimal("100"), Decimal("0.001"), Decimal("0.0002"))
    broker.open_long(plan(), quote("2499.80", "2500"), client_order_id="entry-1")
    candle = Candle(
        symbol="PAXGUSDT",
        timeframe="15m",
        open_time=NOW,
        close_time=NOW + timedelta(minutes=15),
        open=Decimal("2475"),
        high=Decimal("2482"),
        low=Decimal("2470"),
        close=Decimal("2478"),
        volume=Decimal("10"),
        closed=True,
    )

    trade = broker.process_candle(candle, client_order_id="exit-gap")

    assert trade is not None
    assert trade.exit_fill.price == Decimal("2474.5050")
