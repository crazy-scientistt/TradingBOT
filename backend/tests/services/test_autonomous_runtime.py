from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path

import pytest
from goldguard.config import Settings
from goldguard.domain.enums import StrategyMode
from goldguard.domain.models import Candle, Quote
from goldguard.domain.profile import default_autonomous_profile
from goldguard.services.autonomous_runtime import AutonomousRuntime
from goldguard.services.runtime_facade import RuntimeFacade
from goldguard.storage.database import Database
from goldguard.storage.repositories import GenomeRepository, ReflectionRepository
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


def test_facade_autonomous_start_does_not_mark_legacy_running(tmp_path: Path) -> None:
    db = Database(tmp_path / "auto.db")
    db.migrate()
    genomes = GenomeRepository(db)
    genomes.save_genome(trend_pullback_v1(), origin="baseline", status="active")
    settings = Settings(paper_starting_balance=Decimal("100"))
    auto = AutonomousRuntime(
        settings=settings,
        database=db,
        profile=default_autonomous_profile(),
        genome_repo=genomes,
        reflection_repo=ReflectionRepository(db),
    )

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


@pytest.mark.asyncio
async def test_autonomous_hold_without_history_does_not_open(tmp_path: Path) -> None:
    db = Database(tmp_path / "auto2.db")
    db.migrate()
    genomes = GenomeRepository(db)
    genomes.save_genome(trend_pullback_v1(), origin="baseline", status="active")
    runtime = AutonomousRuntime(
        settings=Settings(paper_starting_balance=Decimal("100")),
        database=db,
        profile=default_autonomous_profile(),
        genome_repo=genomes,
        reflection_repo=ReflectionRepository(db),
    )
    runtime.start()
    quote = Quote(bid=Decimal("2500"), ask=Decimal("2501"), observed_at=datetime.now(UTC))
    await runtime.on_closed_candle(_candle("ETHUSDT"), quote)
    assert runtime.broker.open_positions() == ()
