import importlib
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from goldguard.ai.gemini import AiAssessment, DecisionRequest
from goldguard.broker.paper import PaperBroker
from goldguard.config import Settings
from goldguard.context.playbook import ProfessionalChecklist
from goldguard.domain.defaults import SAFE_DEFAULT_V1
from goldguard.domain.enums import AiDecision, BotState
from goldguard.domain.models import Candle, Quote
from goldguard.market.binance import SymbolFilters
from goldguard.risk.engine import RiskEngine
from goldguard.risk.state_machine import StateMachine
from goldguard.services.runtime import TradingRuntime
from goldguard.storage.database import Database
from goldguard.storage.repositories import GenomeRepository, LedgerRepository
from goldguard.strategy.genome import trend_pullback_v1
from goldguard.strategy.runtime import GenomeRuntime

START = datetime(2026, 8, 26, 0, 0, tzinfo=UTC)


class ApprovingAsyncVeto:
    async def decide(self, request: DecisionRequest) -> AiAssessment:
        return AiAssessment(
            decision=AiDecision.APPROVE_ENTRY,
            confidence=86,
            reason_codes=("TREND_ALIGNED", "LIQUIDITY_GOOD"),
            rationale="Approved in test.",
            memory_refs=(),
            prompt_hash="runtime-test",
            model="test-veto",
        )


def make_symbol_filters() -> SymbolFilters:
    return SymbolFilters(
        tick_size=Decimal("0.01"),
        step_size=Decimal("0.0001"),
        minimum_quantity=Decimal("0.0001"),
        maximum_quantity=Decimal("100"),
        minimum_notional=Decimal("5"),
    )


def make_market_history() -> tuple[list[Candle], list[Candle], Candle, Quote]:
    candles_15m: list[Candle] = []
    history_close_values = [2400 + (index * 0.45) for index in range(180)] + [
        2440,
        2436,
        2432,
        2428,
        2424,
        2420,
        2416,
        2412,
        2408,
        2404,
        2400,
        2398,
        2396,
        2394,
        2392,
        2390,
        2392,
        2396,
        2390,
        2390,
    ]
    for index, close_value in enumerate(history_close_values):
        open_time = START + timedelta(minutes=15 * index)
        close_time = open_time + timedelta(minutes=15)
        close = Decimal(str(close_value))
        open_price = close - Decimal("1.25")
        candles_15m.append(
            Candle(
                symbol="PAXGUSDT",
                timeframe="15m",
                open_time=open_time,
                close_time=close_time,
                open=open_price,
                high=close + Decimal("2.00"),
                low=open_price - Decimal("1.00"),
                close=close,
                volume=Decimal("20.0") + Decimal(index % 7),
                closed=True,
            )
        )

    candles_1h: list[Candle] = []
    for index in range(50):
        open_time = START + timedelta(hours=index)
        close_time = open_time + timedelta(hours=1)
        close = Decimal("2350.00") + (Decimal(index) * Decimal("2.50"))
        candles_1h.append(
            Candle(
                symbol="PAXGUSDT",
                timeframe="1h",
                open_time=open_time,
                close_time=close_time,
                open=close - Decimal("4.00"),
                high=close + Decimal("3.00"),
                low=close - Decimal("5.00"),
                close=close,
                volume=Decimal("90.0") + Decimal(index),
                closed=True,
            )
        )

    next_open = candles_15m[-1].close_time
    next_close = next_open + timedelta(minutes=15)
    next_candle = Candle(
        symbol="PAXGUSDT",
        timeframe="15m",
        open_time=next_open,
        close_time=next_close,
        open=Decimal("2391.00"),
        high=Decimal("2438.00"),
        low=Decimal("2388.00"),
        close=Decimal("2436.00"),
        volume=Decimal("34.0"),
        closed=True,
    )
    next_quote = Quote(
        bid=next_candle.close - Decimal("0.20"),
        ask=next_candle.close,
        observed_at=next_candle.close_time,
    )
    return candles_15m, candles_1h, next_candle, next_quote


def build_runtime(tmp_path: Path) -> tuple[TradingRuntime, Database]:
    database = Database(tmp_path / "goldguard.db")
    database.migrate()
    genome_repo = GenomeRepository(database)
    ledger_repo = LedgerRepository(database)
    genome_repo.save_genome(trend_pullback_v1(), origin="baseline", status="active")
    ledger_repo.create_paper_session(Decimal("100"))
    runtime = TradingRuntime(
        database=database,
        settings=Settings(environment="test", data_dir=tmp_path),
        broker=PaperBroker(Decimal("100"), Decimal("0.001"), Decimal("0.0002")),
        genome_repo=genome_repo,
        ledger_repo=ledger_repo,
        strategy_runtime=GenomeRuntime(),
        risk_engine=RiskEngine(SAFE_DEFAULT_V1),
        filters=None,
        state_machine=StateMachine(),
        candles_15m=[],
        candles_1h=[],
        latest_quote=Quote(
            bid=Decimal("2500"),
            ask=Decimal("2500.20"),
            observed_at=START,
        ),
        checklist=ProfessionalChecklist(),
        ai_veto=ApprovingAsyncVeto(),
    )
    return runtime, database


def configure_verified_market(runtime: TradingRuntime) -> tuple[Candle, Quote]:
    candles_15m, candles_1h, candle, quote = make_market_history()
    runtime.configure_market_inputs(
        source="test-fixture",
        verified=True,
        filters=make_symbol_filters(),
        candles_15m=candles_15m,
        candles_1h=candles_1h,
        latest_quote=quote,
    )
    return candle, quote


def test_runtime_requires_explicit_verified_market_inputs_before_start(tmp_path) -> None:
    """Start is refused until ingestion has verified real candles. No network here: the
    invariant is the runtime's, not the ingester's."""
    runtime, _ = build_runtime(tmp_path)

    assert runtime.status().market_verified is False
    with pytest.raises(RuntimeError, match="verified market inputs"):
        runtime.start()


def test_runtime_exposes_durable_runtime_error_endpoint(tmp_path) -> None:
    runtime, database = build_runtime(tmp_path)

    identifier = runtime.record_runtime_error("manual runtime failure")

    assert identifier
    with database.connect() as connection:
        row = connection.execute(
            "SELECT component, status, details_json FROM system_health_events WHERE id = ?",
            (identifier,),
        ).fetchone()
    assert row is not None
    assert row["component"] == "trading_runtime"
    assert row["status"] == "error"


def test_runtime_processes_closed_candle_once_and_persists_decision_records(tmp_path) -> None:
    runtime, database = build_runtime(tmp_path)
    candle, quote = configure_verified_market(runtime)

    runtime.start()
    outcome = runtime.process_closed_candle(candle, quote)

    assert outcome.executed is True
    assert outcome.fill is not None
    with database.connect() as connection:
        state_transitions = connection.execute(
            "SELECT from_state, to_state, reason FROM state_transitions ORDER BY id"
        ).fetchall()
        context_count = connection.execute("SELECT count(*) FROM context_snapshots").fetchone()[0]
        ai_count = connection.execute("SELECT count(*) FROM ai_decisions").fetchone()[0]
        risk_count = connection.execute("SELECT count(*) FROM risk_decisions").fetchone()[0]
        decision_count = connection.execute("SELECT count(*) FROM decision_chains").fetchone()[0]

    assert decision_count == 1
    assert context_count == 1
    assert ai_count == 1
    assert risk_count == 1
    assert [(row["from_state"], row["to_state"]) for row in state_transitions] == [
        ("PAPER_READY", "RUNNING_FLAT"),
        ("RUNNING_FLAT", "RUNNING_OPEN"),
    ]


def test_runtime_pause_and_resume_with_open_position_returns_to_running_open(tmp_path) -> None:
    runtime, _database = build_runtime(tmp_path)
    candle, quote = configure_verified_market(runtime)

    runtime.start()
    runtime.process_closed_candle(candle, quote)
    runtime.pause()

    assert runtime.status().state is BotState.COOLDOWN
    runtime.start()
    assert runtime.status().state is BotState.RUNNING_OPEN
    assert runtime.status().paused is False


def test_runtime_rehydrates_open_position_and_cash_after_restart(tmp_path) -> None:
    runtime, database = build_runtime(tmp_path)
    candle, quote = configure_verified_market(runtime)

    runtime.start()
    runtime.process_closed_candle(candle, quote)
    cash_after_entry = runtime._broker.cash
    stop_quote = Quote(
        bid=Decimal("1.00"),
        ask=Decimal("1.10"),
        observed_at=quote.observed_at + timedelta(seconds=30),
    )
    runtime.shutdown()

    rehydrated = TradingRuntime(
        database=database,
        settings=Settings(environment="test", data_dir=tmp_path),
        broker=PaperBroker(Decimal("100"), Decimal("0.001"), Decimal("0.0002")),
        genome_repo=GenomeRepository(database),
        ledger_repo=LedgerRepository(database),
        strategy_runtime=GenomeRuntime(),
        risk_engine=RiskEngine(SAFE_DEFAULT_V1),
        filters=None,
        state_machine=StateMachine(),
        candles_15m=[],
        candles_1h=[],
        latest_quote=quote,
        checklist=ProfessionalChecklist(),
        ai_veto=ApprovingAsyncVeto(),
    )
    configure_verified_market(rehydrated)

    assert rehydrated.status().has_position is True
    assert rehydrated._broker.cash == cash_after_entry
    closed = rehydrated.process_quote(stop_quote)
    assert closed is not None
    assert closed.closed_trade is not None


def test_web_runtime_preserves_halted_flag_across_process_restart(
    tmp_path,
    monkeypatch,
) -> None:
    monkeypatch.setenv("GOLDGUARD_ENVIRONMENT", "test")
    monkeypatch.setenv("GOLDGUARD_DATA_DIR", str(tmp_path))

    import goldguard.web.app as web_module

    first_app = importlib.reload(web_module)
    with TestClient(first_app.app):
        runtime = first_app.get_trading_runtime()
        configure_verified_market(runtime)
        runtime.start()
        runtime.stop()
        assert runtime.status().halted is True

    restarted_app = importlib.reload(web_module)
    with TestClient(restarted_app.app):
        runtime = restarted_app.get_trading_runtime()
        assert runtime.status().halted is True
        with pytest.raises(RuntimeError, match="halted"):
            runtime.start()
