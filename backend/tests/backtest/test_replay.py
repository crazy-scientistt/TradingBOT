from datetime import UTC, datetime, timedelta
from decimal import Decimal

from goldguard.backtest.replay import ReplayEngine, chronological_partitions
from goldguard.broker.paper import PaperBroker
from goldguard.domain.models import Candle, TradePlan

START = datetime(2026, 1, 1, tzinfo=UTC)


def candle(index: int, *, open_: str, high: str, low: str, close: str) -> Candle:
    opened = START + timedelta(minutes=15 * index)
    return Candle(
        symbol="PAXGUSDT",
        timeframe="15m",
        open_time=opened,
        close_time=opened + timedelta(minutes=15),
        open=Decimal(open_),
        high=Decimal(high),
        low=Decimal(low),
        close=Decimal(close),
        volume=Decimal("10"),
        closed=True,
    )


def test_replay_signal_sees_only_closed_history_and_enters_on_next_bar() -> None:
    candles = (
        candle(0, open_="99", high="101", low="98", close="100"),
        candle(1, open_="101", high="110", low="95", close="108"),
        candle(2, open_="108", high="121", low="107", close="120"),
        candle(3, open_="120", high="122", low="119", close="121"),
    )
    seen_histories: list[tuple[Decimal, ...]] = []

    def signal(history: tuple[Candle, ...]) -> TradePlan | None:
        seen_histories.append(tuple(item.close for item in history))
        if len(history) == 1:
            return TradePlan(
                entry=Decimal("100"),
                stop=Decimal("90"),
                target=Decimal("120"),
                quantity=Decimal("0.5"),
                risk_amount=Decimal("5"),
                expected_fees=Decimal("0"),
            )
        return None

    result = ReplayEngine(PaperBroker(Decimal("100"), Decimal("0"), Decimal("0"))).run(
        candles,
        entry_signal=signal,
    )

    assert seen_histories[0] == (Decimal("100"),)
    assert all(
        history == tuple(item.close for item in candles[: len(history)])
        for history in seen_histories
    )
    assert len(result.trades) == 1
    assert result.trades[0].entry_fill.filled_at == candles[1].open_time
    assert result.trades[0].entry_fill.price == Decimal("101")
    assert result.trades[0].exit_fill.price == Decimal("120")
    assert (
        result.run_hash
        == ReplayEngine(PaperBroker(Decimal("100"), Decimal("0"), Decimal("0")))
        .run(candles, entry_signal=signal)
        .run_hash
    )


def test_chronological_partitions_are_non_overlapping_and_preserve_order() -> None:
    partitions = chronological_partitions(tuple(range(20)))

    assert partitions.development == tuple(range(14))
    assert partitions.validation == tuple(range(14, 17))
    assert partitions.holdout == tuple(range(17, 20))
    assert partitions.development + partitions.validation + partitions.holdout == tuple(range(20))
