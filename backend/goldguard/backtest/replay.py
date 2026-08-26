import hashlib
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal

from goldguard.broker.base import ClosedPaperTrade
from goldguard.broker.paper import PaperBroker
from goldguard.domain.models import Candle, Quote, TradePlan
from goldguard.market.history import verify_candles

EntrySignal = Callable[[tuple[Candle, ...]], TradePlan | None]


@dataclass(frozen=True)
class ChronologicalPartitions[T]:
    development: tuple[T, ...]
    validation: tuple[T, ...]
    holdout: tuple[T, ...]


@dataclass(frozen=True)
class ReplayEquityPoint:
    event_time: datetime
    equity: Decimal


@dataclass(frozen=True)
class ReplayResult:
    trades: tuple[ClosedPaperTrade, ...]
    equity_curve: tuple[ReplayEquityPoint, ...]
    final_equity: Decimal
    run_hash: str


def chronological_partitions[T](items: Sequence[T]) -> ChronologicalPartitions[T]:
    """Split ordered observations into exact, non-overlapping 70/15/15 windows."""
    values = tuple(items)
    development_end = len(values) * 70 // 100
    validation_end = development_end + len(values) * 15 // 100
    return ChronologicalPartitions(
        development=values[:development_end],
        validation=values[development_end:validation_end],
        holdout=values[validation_end:],
    )


class ReplayEngine:
    """Feeds closed candles in event-time order and delays signals by one bar."""

    def __init__(self, broker: PaperBroker) -> None:
        self._broker = broker

    def run(
        self,
        candles: Sequence[Candle],
        *,
        entry_signal: EntrySignal,
    ) -> ReplayResult:
        ordered = tuple(candles)
        self._validate_dataset(ordered)
        history: list[Candle] = []
        trades: list[ClosedPaperTrade] = []
        equity_curve: list[ReplayEquityPoint] = []
        pending_plan: TradePlan | None = None

        for index, candle in enumerate(ordered):
            if pending_plan is not None and self._broker.position is None:
                opening_quote = Quote(
                    bid=candle.open,
                    ask=candle.open,
                    observed_at=candle.open_time,
                )
                self._broker.open_long(
                    pending_plan,
                    opening_quote,
                    client_order_id=f"replay-entry-{index}",
                )
                pending_plan = None

            closed_trade = self._broker.process_candle(
                candle,
                client_order_id=f"replay-exit-{index}",
            )
            if closed_trade is not None:
                trades.append(closed_trade)

            closing_quote = Quote(
                bid=candle.close,
                ask=candle.close,
                observed_at=candle.close_time,
            )
            equity_curve.append(
                ReplayEquityPoint(candle.close_time, self._broker.equity(closing_quote))
            )
            history.append(candle)
            if self._broker.position is None and pending_plan is None:
                pending_plan = entry_signal(tuple(history))

        final_quote = Quote(
            bid=ordered[-1].close,
            ask=ordered[-1].close,
            observed_at=ordered[-1].close_time,
        )
        final_equity = self._broker.equity(final_quote)
        return ReplayResult(
            trades=tuple(trades),
            equity_curve=tuple(equity_curve),
            final_equity=final_equity,
            run_hash=self._run_hash(ordered, trades, final_equity),
        )

    @staticmethod
    def _validate_dataset(candles: tuple[Candle, ...]) -> None:
        if not candles:
            raise ValueError("replay requires at least one closed candle")
        if any(candle.open_time.tzinfo is None for candle in candles):
            raise ValueError("replay candles must be timezone-aware")
        if tuple(sorted(candles, key=lambda item: item.open_time)) != candles:
            raise ValueError("replay candles must be chronological")
        timeframe = candles[0].timeframe
        if not verify_candles(candles, timeframe).verified:
            raise ValueError("replay candles must be closed, unique, and contiguous")

    @staticmethod
    def _run_hash(
        candles: tuple[Candle, ...],
        trades: list[ClosedPaperTrade],
        final_equity: Decimal,
    ) -> str:
        digest = hashlib.sha256()
        for candle in candles:
            digest.update(
                "|".join(
                    (
                        candle.open_time.astimezone(UTC).isoformat(),
                        str(candle.open),
                        str(candle.high),
                        str(candle.low),
                        str(candle.close),
                        str(candle.volume),
                    )
                ).encode()
            )
            digest.update(b"\n")
        for trade in trades:
            digest.update(
                f"{trade.entry_fill.price}|{trade.exit_fill.price}|"
                f"{trade.realized_pnl}|{trade.exit_reason.value}\n".encode()
            )
        digest.update(f"final-equity|{final_equity}\n".encode())
        return digest.hexdigest()
