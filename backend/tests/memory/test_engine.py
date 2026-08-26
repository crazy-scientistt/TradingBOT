from decimal import Decimal
from pathlib import Path

import pytest
from goldguard.memory.engine import MemoryBank
from goldguard.memory.reflections import ReflectionEngine, TradeOutcome
from goldguard.storage.database import Database
from goldguard.storage.repositories import ReflectionRepository


@pytest.fixture
def database(tmp_path: Path) -> Database:
    db = Database(tmp_path / "goldguard.db")
    db.migrate()
    return db


def test_memory_bank_dual_namespace_and_query_relevant(database: Database) -> None:
    repo = ReflectionRepository(database)
    bank = MemoryBank(repo)
    engine = ReflectionEngine()

    # Add historical reflections
    h_out = TradeOutcome(
        trade_id="h-trade-1",
        namespace="historical",
        hypothesis="Trend breakout",
        realized_pnl=Decimal("3.50"),
        maximum_adverse_excursion=Decimal("-0.20"),
        maximum_favorable_excursion=Decimal("3.60"),
        fees=Decimal("0.20"),
        exit_reason="TAKE_PROFIT",
        regime_tags=("trend", "low-volatility"),
        context_error=False,
        rule_adherent=True,
    )
    bank.record_reflection(engine.create(h_out))

    # Add forward reflections
    f_out1 = TradeOutcome(
        trade_id="f-trade-1",
        namespace="forward",
        hypothesis="Pullback",
        realized_pnl=Decimal("-1.20"),
        maximum_adverse_excursion=Decimal("-1.20"),
        maximum_favorable_excursion=Decimal("0.10"),
        fees=Decimal("0.15"),
        exit_reason="STOP_LOSS",
        regime_tags=("trend", "normal-volatility"),
        context_error=False,
        rule_adherent=True,
    )
    bank.record_reflection(engine.create(f_out1))

    # Query forward reflections matching regime
    summaries = bank.query_relevant_summaries(
        namespace="forward",
        regime_tags=("trend", "normal-volatility"),
        limit=3,
    )

    assert len(summaries) == 1
    assert summaries[0]["lesson_code"] == "STOP_HIT_EXPANSION"
    assert summaries[0]["exit_reason"] == "STOP_LOSS"
    assert Decimal(str(summaries[0]["net_pnl"])) == Decimal("-1.20")
