from datetime import UTC, datetime, timedelta
from decimal import Decimal

from goldguard.backtest.engine import BacktestEngine, FrictionConfig
from goldguard.domain.enums import ExitReason
from goldguard.domain.models import Candle
from goldguard.strategy.genome import trend_pullback_v1

START = datetime(2026, 1, 1, tzinfo=UTC)


def make_candle(
    index: int,
    *,
    open_: str,
    high: str,
    low: str,
    close: str,
    volume: str = "10",
    timeframe: str = "15m",
) -> Candle:
    step = timedelta(minutes=15 if timeframe == "15m" else 60)
    opened = START + (step * index)
    return Candle(
        symbol="PAXGUSDT",
        timeframe=timeframe,
        open_time=opened,
        close_time=opened + step - timedelta(milliseconds=1),
        open=Decimal(open_),
        high=Decimal(high),
        low=Decimal(low),
        close=Decimal(close),
        volume=Decimal(volume),
        closed=True,
    )


def test_backtest_engine_identical_input_produces_identical_run_hash() -> None:
    # Build synthetic 15m candles
    candles_15m = [
        make_candle(i, open_="2500", high="2505", low="2495", close="2502") for i in range(250)
    ]
    # Synthetic 1h candles
    candles_1h = [
        make_candle(i, open_="2500", high="2510", low="2490", close="2505", timeframe="1h")
        for i in range(70)
    ]

    genome = trend_pullback_v1()
    engine = BacktestEngine()

    res1 = engine.run(genome, candles_15m, candles_1h)
    res2 = engine.run(genome, candles_15m, candles_1h)

    assert res1.run_hash == res2.run_hash
    assert res1.report.net_pnl == res2.report.net_pnl
    assert res1.report.trade_count == res2.report.trade_count


def test_intrabar_collision_resolves_to_stop_hit_first() -> None:
    zero_friction = FrictionConfig(
        commission_rate=Decimal("0"),
        slippage_rate=Decimal("0"),
        half_spread_rate=Decimal("0"),
    )
    engine = BacktestEngine(zero_friction)
    # Single position entry candle followed by extreme bar touching both stop and target
    collision_candle = make_candle(1, open_="2500", high="2550", low="2470", close="2500")

    trade = engine._simulate_candle_exit(
        entry_price=Decimal("2500"),
        stop_price=Decimal("2485"),
        target_price=Decimal("2530"),
        quantity=Decimal("1"),
        candle=collision_candle,
        opened_at=START,
        friction=zero_friction,
    )

    assert trade is not None
    # Conservative rule: STOP HIT FIRST
    assert trade.exit_reason == ExitReason.STOP_LOSS
    assert trade.exit_fill.price == Decimal("2485")


def test_fee_drag_and_slippage_accounting() -> None:
    friction = FrictionConfig(
        commission_rate=Decimal("0.001"),  # 0.1%
        slippage_rate=Decimal("0.0002"),  # 2 bps
        half_spread_rate=Decimal("0.0002"),  # 2 bps
    )
    engine = BacktestEngine(friction)
    # Candle that hits target cleanly: high reaches 2535
    target_candle = make_candle(1, open_="2500", high="2535", low="2498", close="2530")

    trade = engine._simulate_candle_exit(
        entry_price=Decimal("2500"),
        stop_price=Decimal("2485"),
        target_price=Decimal("2530"),
        quantity=Decimal("1"),
        candle=target_candle,
        opened_at=START,
        friction=friction,
    )

    assert trade is not None
    assert trade.exit_reason == ExitReason.TAKE_PROFIT
    assert trade.realized_pnl < Decimal("30")  # Gross is $30, net must be < $30 due to friction
