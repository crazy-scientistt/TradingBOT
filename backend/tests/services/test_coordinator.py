from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path

import pytest
from goldguard.ai.gemini import AiAssessment, DecisionRequest
from goldguard.broker.paper import PaperBroker
from goldguard.context.models import ContextItem, ContextSnapshot, ContextSource
from goldguard.context.playbook import ChecklistInputs, ChecklistResult
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


def fresh_context(now: datetime) -> ContextSnapshot:
    return ContextSnapshot.build(
        fetched_at=now,
        sources=(
            ContextSource(
                url="https://www.federalreserve.gov/monetarypolicy/fomccalendars.htm",
                title="FOMC calendar",
                published_at=now,
            ),
        ),
        items=(
            ContextItem(
                summary="No blocking macro event is active for the current paper candle.",
                driver="rates",
                direction="neutral",
                severity="low",
                published_at=now,
                source_indexes=(0,),
                contradictory=False,
            ),
        ),
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
        def evaluate(self, inputs: ChecklistInputs) -> ChecklistResult:
            assert inputs.context.items
            return ChecklistResult(ChecklistAction.PASS, ("PRO_CHECKLIST_PASSED",))

    class MockAiVeto:
        def decide(self, request: DecisionRequest) -> AiAssessment:
            assert request.strategy_version == "trend-pullback-v1"
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
        context_snapshot=fresh_context(candle_close),
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
        context_snapshot=fresh_context(candle_close),
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
        ai_veto=None,  # Not consulted during monitoring!
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


def _entry_features() -> StrategyFeatures:
    return StrategyFeatures(
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


def _record_loss(
    database: Database,
    *,
    account_id: str,
    trade_id: str,
    realized_pnl: str,
    closed_at: datetime,
) -> None:
    with database.transaction() as connection:
        connection.execute(
            """
            INSERT INTO orders(
                id, mode, paper_account_id, client_order_id, side,
                quantity_text, status, created_at
            ) VALUES (?, 'paper', ?, ?, 'BUY', '0.01', 'FILLED', ?)
            """,
            (f"o-{trade_id}", account_id, f"c-{trade_id}", closed_at.isoformat()),
        )
        connection.execute(
            """
            INSERT INTO trades(
                id, mode, paper_account_id, entry_order_id, status,
                realized_pnl_text, opened_at, closed_at
            ) VALUES (?, 'paper', ?, ?, 'CLOSED', ?, ?, ?)
            """,
            (
                trade_id,
                account_id,
                f"o-{trade_id}",
                realized_pnl,
                closed_at.isoformat(),
                closed_at.isoformat(),
            ),
        )


def _coordinator(
    database: Database,
    symbol_filters: SymbolFilters,
) -> tuple[TradingCoordinator, PaperBroker]:
    broker = PaperBroker(Decimal("100"), Decimal("0.001"), Decimal("0.0002"))
    genome_repo = GenomeRepository(database)
    genome_repo.save_genome(trend_pullback_v1(), origin="baseline", status="active")

    class PassChecklist:
        def evaluate(self, inputs: ChecklistInputs) -> ChecklistResult:
            return ChecklistResult(ChecklistAction.PASS, ("PRO_CHECKLIST_PASSED",))

    coordinator = TradingCoordinator(
        broker=broker,
        genome_repo=genome_repo,
        ledger_repo=LedgerRepository(database),
        runtime=GenomeRuntime(),
        risk_engine=RiskEngine(SAFE_DEFAULT_V1),
        checklist=PassChecklist(),
        ai_veto=None,
        filters=symbol_filters,
    )
    return coordinator, broker


def test_recorded_loss_streak_halts_entry(
    database: Database,
    symbol_filters: SymbolFilters,
) -> None:
    """The loss-streak breaker must fire off measured trades, not a hard-coded zero."""
    candle_close = datetime(2026, 8, 26, 0, 15, tzinfo=UTC)
    coordinator, broker = _coordinator(database, symbol_filters)
    account = LedgerRepository(database).create_paper_session(Decimal("100"))
    for index in range(SAFE_DEFAULT_V1.consecutive_loss_limit):
        _record_loss(
            database,
            account_id=account,
            trade_id=f"loss-{index}",
            realized_pnl="-1.00",
            # Older than the cooldown so only the streak can be the blocking reason.
            closed_at=candle_close - timedelta(hours=12 + index),
        )

    outcome = coordinator.scan_closed_candle(
        symbol="PAXGUSDT",
        closed_at=candle_close,
        quote=Quote(bid=Decimal("2503.80"), ask=Decimal("2504.00"), observed_at=candle_close),
        features=_entry_features(),
        context_snapshot=fresh_context(candle_close),
        account_scope=account,
    )

    assert outcome.executed is False
    assert outcome.action == "RISK_REJECTED"
    assert "LOSS_STREAK_COOLDOWN" in outcome.reason_codes
    assert broker.position is None


def test_recent_exit_halts_entry_until_the_cooldown_elapses(
    database: Database,
    symbol_filters: SymbolFilters,
) -> None:
    candle_close = datetime(2026, 8, 26, 0, 15, tzinfo=UTC)
    coordinator, broker = _coordinator(database, symbol_filters)
    account = LedgerRepository(database).create_paper_session(Decimal("100"))
    _record_loss(
        database,
        account_id=account,
        trade_id="just-won",
        realized_pnl="2.00",
        closed_at=candle_close - timedelta(minutes=5),
    )

    outcome = coordinator.scan_closed_candle(
        symbol="PAXGUSDT",
        closed_at=candle_close,
        quote=Quote(bid=Decimal("2503.80"), ask=Decimal("2504.00"), observed_at=candle_close),
        features=_entry_features(),
        context_snapshot=fresh_context(candle_close),
        account_scope=account,
    )

    assert outcome.action == "RISK_REJECTED"
    assert "POST_EXIT_COOLDOWN" in outcome.reason_codes
    assert broker.position is None


def test_clean_ledger_leaves_the_breakers_open(
    database: Database,
    symbol_filters: SymbolFilters,
) -> None:
    """No trade has ever closed, so there is no cooldown or streak to serve."""
    candle_close = datetime(2026, 8, 26, 0, 15, tzinfo=UTC)
    coordinator, broker = _coordinator(database, symbol_filters)
    account = LedgerRepository(database).create_paper_session(Decimal("100"))

    outcome = coordinator.scan_closed_candle(
        symbol="PAXGUSDT",
        closed_at=candle_close,
        quote=Quote(bid=Decimal("2503.80"), ask=Decimal("2504.00"), observed_at=candle_close),
        features=_entry_features(),
        context_snapshot=fresh_context(candle_close),
        account_scope=account,
    )

    assert outcome.executed is True, outcome.reason_codes
    assert broker.position is not None
