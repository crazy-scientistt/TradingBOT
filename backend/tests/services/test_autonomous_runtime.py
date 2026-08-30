from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path

import pytest
from goldguard.config import Settings
from goldguard.domain.enums import ExecutionMode, OrderSide, ProductKind, StrategyMode
from goldguard.domain.models import Candle, Quote
from goldguard.domain.profile import default_autonomous_profile
from goldguard.execution.models import OrderIntent
from goldguard.services.autonomous_runtime import AutonomousRuntime
from goldguard.services.runtime_facade import RuntimeFacade
from goldguard.storage.database import Database
from goldguard.storage.repositories import GenomeRepository, LedgerRepository, ReflectionRepository
from goldguard.strategy.genome import trend_pullback_v1


def _candle(symbol: str, close: str = "2500") -> Candle:
    close_time = datetime(2026, 8, 30, 12, 15, tzinfo=UTC)
    return Candle(
        symbol=symbol,
        timeframe="15m",
        open_time=close_time - timedelta(minutes=15),
        close_time=close_time,
        open=Decimal(close),
        high=Decimal(close) + Decimal("10"),
        low=Decimal(close) - Decimal("10"),
        close=Decimal(close),
        volume=Decimal("12"),
        closed=True,
    )


def _runtime(tmp_path: Path) -> AutonomousRuntime:
    db = Database(tmp_path / "auto.db")
    db.migrate()
    genomes = GenomeRepository(db)
    genomes.save_genome(trend_pullback_v1(), origin="baseline", status="active")
    return AutonomousRuntime(
        settings=Settings(paper_starting_balance=Decimal("100")),
        database=db,
        profile=default_autonomous_profile(),
        genome_repo=genomes,
        reflection_repo=ReflectionRepository(db),
    )


def test_facade_autonomous_start_does_not_mark_legacy_running(tmp_path: Path) -> None:
    auto = _runtime(tmp_path)

    class Legacy:
        def __init__(self) -> None:
            self.started = False

        def start(self) -> None:
            self.started = True

        def pause(self) -> None:
            return None

        def stop(self) -> None:
            return None

        def shutdown(self) -> None:
            return None

        def status(self):
            from types import SimpleNamespace

            from goldguard.domain.enums import BotState

            return SimpleNamespace(
                state=BotState.PAPER_READY,
                running=self.started,
                paused=not self.started,
                halted=False,
                has_position=False,
                paper_account_id="legacy",
                market_verified=False,
                market_source="test",
                degraded_reasons=(),
                rehydration_error=None,
            )

        def recent_events(self, limit: int = 30):
            return ()

    legacy = Legacy()
    facade = RuntimeFacade(
        profile=default_autonomous_profile(),
        legacy=legacy,  # type: ignore[arg-type]
        autonomous=auto,
    )
    assert facade.owner is StrategyMode.AUTONOMOUS
    facade.start()
    assert legacy.started is False
    assert facade.status().running is True
    assert auto.broker.open_positions() == ()
    assert facade.recent_events()


@pytest.mark.asyncio
async def test_autonomous_hold_without_history_does_not_open(tmp_path: Path) -> None:
    runtime = _runtime(tmp_path)
    runtime.start()
    quote = Quote(bid=Decimal("2500"), ask=Decimal("2501"), observed_at=datetime.now(UTC))
    await runtime.on_closed_candle(_candle("ETHUSDT"), quote)
    assert runtime.broker.open_positions() == ()


@pytest.mark.asyncio
async def test_autonomous_stop_flattens_open_spot(tmp_path: Path) -> None:
    runtime = _runtime(tmp_path)
    runtime.start()
    runtime._spot.on_price("ETHUSDT", Decimal("2500"))
    await runtime._spot.submit(
        OrderIntent(
            intent_id="flatten-1",
            client_order_id="flatten-1",
            mode=ExecutionMode.PAPER,
            product=ProductKind.SPOT,
            symbol="ETHUSDT",
            side=OrderSide.BUY,
            quantity=Decimal("0.01"),
            price=Decimal("2500"),
        )
    )
    assert runtime.broker.open_positions()
    runtime.stop()
    await runtime._flatten()
    assert runtime.broker.open_positions() == ()
    assert runtime.status().halted is True


def test_start_records_paper_equity_snapshot(tmp_path: Path) -> None:
    runtime = _runtime(tmp_path)
    runtime.start()
    account = runtime.status().paper_account_id
    rows = LedgerRepository(runtime._database).list_equity_snapshots(account)
    assert rows
    assert Decimal(str(rows[-1]["equity_text"])) == Decimal("100")
    assert Decimal(str(rows[-1]["cash_text"])) == Decimal("100")


@pytest.mark.asyncio
async def test_corrupt_dataset_does_not_block_live_eval(tmp_path: Path) -> None:
    runtime = _runtime(tmp_path)
    runtime.set_dataset_status(lambda: "CORRUPT")
    runtime.start()
    quote = Quote(bid=Decimal("2500"), ask=Decimal("2501"), observed_at=datetime.now(UTC))
    await runtime.on_closed_candle(_candle("ETHUSDT"), quote)
    evals = runtime._last_evals["ETHUSDT"]
    assert evals["action"] in {"HOLD", "ENTER"}
    assert evals["reason"] != "dataset_corrupt"
    ledger = LedgerRepository(runtime._database)
    decisions = ledger.list_decisions(limit=10)
    assert decisions
    assert decisions[0]["symbol"] == "ETHUSDT"
    events = runtime.recent_events()
    assert any(event.payload.get("symbol") == "ETHUSDT" for event in events)


@pytest.mark.asyncio
async def test_evaluate_latest_bars_scores_seeded_history(tmp_path: Path) -> None:
    runtime = _runtime(tmp_path)
    runtime.seed_history("ETHUSDT", [_candle("ETHUSDT")], [])
    runtime.start()
    await runtime.evaluate_latest_bars()
    assert "ETHUSDT" in runtime._last_evals
    assert LedgerRepository(runtime._database).list_decisions()
