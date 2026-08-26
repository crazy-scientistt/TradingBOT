from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

import pytest
from goldguard.ai.gemini import AiAssessment
from goldguard.broker.paper import PaperBroker
from goldguard.context.playbook import ChecklistResult
from goldguard.domain.defaults import SAFE_DEFAULT_V1
from goldguard.domain.enums import AiDecision, ChecklistAction, ExitReason
from goldguard.domain.models import Quote, TradePlan
from goldguard.market.binance import SymbolFilters
from goldguard.risk.engine import RiskEngine
from goldguard.services.coordinator import TradingCoordinator
from goldguard.storage.database import Database
from goldguard.storage.repositories import GenomeRepository, LedgerRepository
from goldguard.strategy.engine import StrategyFeatures
from goldguard.strategy.genome import trend_pullback_v1
from goldguard.strategy.runtime import GenomeRuntime


@pytest.fixture
def database(tmp_path: Path) -> Database:
    db = Database(tmp_path / "goldguard.db")
    db.migrate()
    return db


@pytest.fixture
def symbol_filters() -> SymbolFilters:
    return SymbolFilters(
        tick_size=Decimal("0.01"),
        step_size=Decimal("0.0001"),
        minimum_quantity=Decimal("0.0001"),
        maximum_quantity=Decimal("100"),
        minimum_notional=Decimal("5"),
    )


def test_coordinator_full_pipeline_entry_and_idempotency(
    database: Database,
    symbol_filters: SymbolFilters,
) -> None:
    broker = PaperBroker(Decimal("100"), Decimal("0.001"), Decimal("0.0002"))
    genome_repo = GenomeRepository(database)
    ledger_repo = LedgerRepository(database)
    runtime = GenomeRuntime()
    risk_engine = RiskEngine(SAFE_DEFAULT_V1)

    genome_repo.save_genome(trend_pullback_v1(), origin="baseline", status="active")

    class MockEvidenceChecklist:
        def evaluate(self, *args, **kwargs) -> ChecklistResult:
            return ChecklistResult(ChecklistAction.PASS, ("PRO_CHECKLIST_PASSED",))

    class MockAiVeto:
        def decide(self, *args, **kwargs) -> AiAssessment:
            return AiAssessment(
                decision=AiDecision.APPROVE_ENTRY,
                confidence=85,
                reason_codes=("STRONG_TREND_CONFIRMED",),
                rationale="Approved by AI veto",
                memory_refs=(),
                prompt_hash="h123",
                model="google-antigravity/gemini-3.7-flash",
            )

    coordinator = TradingCoordinator(
        broker=broker,
        genome_repo=genome_repo,
        ledger_repo=ledger_repo,
        runtime=runtime,
        risk_engine=risk_engine,
        checklist=MockEvidenceChecklist(),
        ai_veto=MockAiVeto(),
        filters=symbol_filters,
    )

    candle_close = datetime(2026, 8, 26, 0, 15, tzinfo=UTC)
    features = StrategyFeatures(
        previous_close=2498.0,
        latest_close=2504.0,
        ema20_15m=2500.0,
        ema50_15m=2488.0,
        previous_rsi14=44.0,
        rsi14=50.0,
        atr14=12.0,
        atr_rate=0.0048,
        volume_ratio=1.1,
        spread_rate=0.0004,
        latest_close_1h=2502.0,
        ema50_1h=2475.0,
        ema200_1h=2400.0,
        ema50_slope_1h=0.002,
        consecutive_closes_below_ema50=0,
        sufficient_history=True,
        contiguous=True,
        quote_fresh=True,
    )
    quote = Quote(bid=Decimal("2503.80"), ask=Decimal("2504.00"), observed_at=candle_close)

    # First scan creates position
    outcome = coordinator.scan_closed_candle(
        symbol="PAXGUSDT",
        closed_at=candle_close,
        quote=quote,
        features=features,
    )

    assert outcome.executed is True
    assert outcome.action == "ENTRY_FILLED"
    assert broker.position is not None

    # Repeated scan with same closed_at is idempotent and cannot duplicate order
    second_outcome = coordinator.scan_closed_candle(
        symbol="PAXGUSDT",
        closed_at=candle_close,
        quote=quote,
        features=features,
    )
    assert second_outcome.action in ("ALREADY_PROCESSED", "POSITION_ALREADY_OPEN")
    assert broker.position is not None


def test_monitor_open_position_fast_protection_path(
    database: Database,
    symbol_filters: SymbolFilters,
) -> None:
    broker = PaperBroker(Decimal("100"), Decimal("0.001"), Decimal("0.0002"))
    plan = TradePlan(
        entry=Decimal("2500"),
        stop=Decimal("2485.00"),
        target=Decimal("2530.00"),
        quantity=Decimal("0.033"),
        risk_amount=Decimal("0.495"),
        expected_fees=Decimal("0.165"),
    )
    fill_quote = Quote(
        bid=Decimal("2499.80"), ask=Decimal("2500"), observed_at=datetime(2026, 8, 26, tzinfo=UTC)
    )
    broker.open_long(plan, fill_quote, client_order_id="test-pos")

    coordinator = TradingCoordinator(
        broker=broker,
        genome_repo=GenomeRepository(database),
        ledger_repo=LedgerRepository(database),
        runtime=GenomeRuntime(),
        risk_engine=RiskEngine(SAFE_DEFAULT_V1),
        checklist=None,  # Not consulted during monitoring!
        ai_veto=None,    # Not consulted during monitoring!
        filters=symbol_filters,
    )

    # Price hits stop loss
    stop_quote = Quote(
        bid=Decimal("2484.00"),
        ask=Decimal("2484.50"),
        observed_at=datetime(2026, 8, 26, 0, 30, tzinfo=UTC),
    )
    exit_outcome = coordinator.monitor_open_position(stop_quote)
    assert exit_outcome is not None
    assert exit_outcome.closed_trade is not None
    assert exit_outcome.closed_trade.exit_reason == ExitReason.STOP_LOSS
    assert broker.position is None
