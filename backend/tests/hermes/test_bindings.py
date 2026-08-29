from __future__ import annotations

from pathlib import Path

import pytest
from goldguard.hermes.bindings import build_tool_bindings
from goldguard.hermes.tools import HermesToolRegistry, SealedHoldoutAccessError
from goldguard.storage.database import Database
from goldguard.storage.repositories import GenomeRepository, MarketCandleRepository
from goldguard.strategy.genome import trend_pullback_v1


@pytest.fixture
def db(tmp_path: Path) -> Database:
    database = Database(tmp_path / "goldguard.db")
    database.migrate()
    return database


@pytest.mark.asyncio
async def test_bound_get_candles_returns_empty_not_synthetic(db: Database) -> None:
    registry = HermesToolRegistry(
        bindings=build_tool_bindings(candle_repo=MarketCandleRepository(db))
    )
    result = await registry.call("get_candles", {"symbol": "PAXGUSDT"})
    assert result["available"] is True
    assert result["candles"] == []


@pytest.mark.asyncio
async def test_bound_submit_genome_stays_candidate(db: Database) -> None:
    genome_repo = GenomeRepository(db)
    registry = HermesToolRegistry(bindings=build_tool_bindings(genome_repo=genome_repo))
    genome = trend_pullback_v1()
    payload = genome.model_dump(mode="json")
    payload["genome_id"] = "hermes-candidate-1"
    result = await registry.call("submit_genome", {"genome": payload})
    assert result["available"] is True
    assert result["status"] == "accepted_candidate"
    stored = genome_repo.get_genome_row("hermes-candidate-1")
    assert stored is not None
    assert stored["status"] == "candidate"
    assert stored["origin"] == "hermes"


@pytest.mark.asyncio
async def test_bound_invalid_genome_is_rejected(db: Database) -> None:
    registry = HermesToolRegistry(
        bindings=build_tool_bindings(genome_repo=GenomeRepository(db))
    )
    result = await registry.call("submit_genome", {"genome": {"genome_id": "x"}})
    assert result["available"] is False
    assert result["status"] == "rejected"


@pytest.mark.asyncio
async def test_bound_holdout_still_sealed(db: Database) -> None:
    registry = HermesToolRegistry(bindings=build_tool_bindings())
    with pytest.raises(SealedHoldoutAccessError):
        await registry.call("get_evaluation", {"partition": "holdout"})


@pytest.mark.asyncio
async def test_bound_backtest_without_candles_does_not_invent_metrics(db: Database) -> None:
    from goldguard.backtest.engine import BacktestEngine, FrictionConfig

    genome_repo = GenomeRepository(db)
    genome_repo.save_genome(trend_pullback_v1(), origin="baseline", status="active")
    registry = HermesToolRegistry(
        bindings=build_tool_bindings(
            candle_repo=MarketCandleRepository(db),
            genome_repo=genome_repo,
            backtest_engine=BacktestEngine(FrictionConfig()),
        )
    )
    result = await registry.call("run_backtest", {"genome_id": "trend-pullback-v1"})
    assert result["available"] is False
    assert result["reason"] == "INSUFFICIENT_CANDLES"
    assert result["trades"] == []
    assert "sharpe" not in result
