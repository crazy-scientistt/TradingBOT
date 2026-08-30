"""Promotion runs on evidence alone, and the controller rolls itself back.

The four gates have their own unit tests; these exercise the controller's job —
sequencing the gates, refusing candidates that loosen a protective bound, persisting
the canary, and reverting to the baseline without a human in the loop.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from goldguard.backtest.engine import BacktestResult
from goldguard.backtest.metrics import PerformanceReport
from goldguard.backtest.walk_forward import WalkForwardReport
from goldguard.services.promotion_controller import (
    CanaryConfig,
    CanaryEvent,
    EvidenceDataset,
    PromotionController,
    ShadowEvidence,
)
from goldguard.storage.database import Database
from goldguard.storage.repositories import (
    AutonomyRepository,
    EvaluationRepository,
    GenomeRepository,
    PromotionRepository,
)
from goldguard.strategy.genome import (
    ExitRules,
    GuardBounds,
    StrategyGenome,
    trend_pullback_v1,
)
from goldguard.strategy.promotion import PromotionPipeline


def _report(
    *,
    net_return: str = "0.08",
    drawdown: str = "0.04",
    trades: int = 40,
    win_rate: str = "0.55",
    profit_factor: str = "1.80",
) -> PerformanceReport:
    net_pnl = Decimal("100") * Decimal(net_return)
    return PerformanceReport(
        initial_equity=Decimal("100"),
        final_equity=Decimal("100") + net_pnl,
        net_pnl=net_pnl,
        gross_pnl=net_pnl + Decimal("1"),
        fee_drag=Decimal("1"),
        net_return=Decimal(net_return),
        annualized_return=None,
        trade_count=trades,
        win_rate=Decimal(win_rate),
        profit_factor=Decimal(profit_factor),
        expectancy=Decimal("0.2"),
        maximum_drawdown=Decimal(drawdown),
        exposure_rate=Decimal("0.3"),
        sharpe_ratio=Decimal("1.1"),
        sortino_ratio=Decimal("1.4"),
        calmar_ratio=Decimal("2.0"),
        buy_and_hold_return=Decimal("0.02"),
        sample_sufficient=True,
    )


def _result(report: PerformanceReport) -> BacktestResult:
    return BacktestResult(
        trades=(),
        report=report,
        equity_curve=(),
        run_hash="stub-run-hash",
        metrics_dict={},
        mae=Decimal("0"),
        mfe=Decimal("0"),
        ulcer_index=Decimal("0"),
    )


class _StubEngine:
    """Replaces the backtest so the gates get a decided report, not a random one."""

    def __init__(self, report: PerformanceReport) -> None:
        self.report = report
        self.calls = 0

    def run(self, genome: StrategyGenome, candles_15m: object, *args: object, **kwargs: object):
        self.calls += 1
        return _result(self.report)


class _StubHarness:
    def __init__(
        self,
        *,
        wfe: str = "0.80",
        dsr: str = "0.99",
        drawdown: str = "0.05",
        holdout: PerformanceReport | None = None,
    ) -> None:
        self.wfe = wfe
        self.dsr = dsr
        self.drawdown = drawdown
        self.holdout = holdout if holdout is not None else _report()
        self.tokens: list[str | None] = []

    def evaluate(
        self,
        *,
        genome: StrategyGenome,
        candles_15m: object,
        windows: object = None,
        unlock_holdout: bool = False,
        promotion_token: str | None = None,
    ) -> WalkForwardReport:
        if unlock_holdout:
            self.tokens.append(promotion_token)
        return WalkForwardReport(
            genome_id=genome.genome_id,
            windows=(),
            aggregate_in_sample_return=Decimal("0.10"),
            aggregate_out_of_sample_return=Decimal("0.08"),
            wfe=Decimal(self.wfe),
            deflated_sharpe_ratio=Decimal(self.dsr),
            pbo=Decimal("0.20"),
            max_out_of_sample_drawdown=Decimal(self.drawdown),
            gate_passed=True,
            gate_failure_reasons=(),
            holdout_evaluated=unlock_holdout,
            holdout_result=_result(self.holdout) if unlock_holdout else None,
        )


def _candidate(
    *,
    genome_id: str = "hermes-candidate-1",
    exit_rules: ExitRules | None = None,
    guard: GuardBounds | None = None,
) -> StrategyGenome:
    base = trend_pullback_v1()
    return base.model_copy(
        update={
            "genome_id": genome_id,
            "parent_id": base.genome_id,
            "evidence_refs": ("parent:trend-pullback-v1", "dataset:paxg-3y"),
            "exit": exit_rules or base.exit,
            "guard": guard or base.guard,
        }
    )


def _dataset(*, verified: bool = True, shadow: ShadowEvidence | None = None) -> EvidenceDataset:
    return EvidenceDataset(
        dataset_id="paxg-3y-15m",
        verified=verified,
        candles_15m=(),
        shadow=shadow
        or ShadowEvidence(
            days=21,
            net_pnl=Decimal("3.20"),
            trades=9,
            slippage_acceptable=True,
        ),
    )


@dataclass
class _Env:
    controller: PromotionController
    genomes: GenomeRepository
    promotions: PromotionRepository
    autonomy: AutonomyRepository
    harness: _StubHarness
    baseline: StrategyGenome


def _env(tmp_path, **harness_kwargs) -> _Env:
    database = Database(tmp_path / "promotion.db")
    database.migrate()
    genomes = GenomeRepository(database)
    promotions = PromotionRepository(database)
    autonomy = AutonomyRepository(database)
    harness = _StubHarness(**harness_kwargs)
    pipeline = PromotionPipeline(
        genome_repo=genomes,
        eval_repo=EvaluationRepository(database),
        promotion_repo=promotions,
    )
    baseline = trend_pullback_v1()
    genomes.save_genome(baseline, origin="baseline", status="active")
    controller = PromotionController(
        pipeline=pipeline,
        genome_repo=genomes,
        promotion_repo=promotions,
        autonomy_repo=autonomy,
        engine=_StubEngine(_report()),
        harness=harness,
    )
    return _Env(controller, genomes, promotions, autonomy, harness, baseline)


@pytest.fixture
def env(tmp_path) -> _Env:
    return _env(tmp_path)


def test_all_gates_passing_promotes_without_human_approval(env: _Env) -> None:
    candidate = _candidate()
    env.genomes.save_genome(candidate, origin="hermes", status="candidate")

    decision = env.controller.evaluate(candidate, _dataset(), env.baseline)

    assert decision.promoted is True, decision.rejection_reasons
    assert decision.promoted_by == "promotion_controller"
    assert decision.stage == "canary"
    assert decision.promotion_id is not None
    assert env.genomes.get_genome_status(candidate.genome_id) == "active"
    # The sealed partition may only be opened with a gate token, and only after validation.
    assert env.harness.tokens and all(
        token is not None and token.startswith("prom_gate_") for token in env.harness.tokens
    )

    canary = env.promotions.get_open_canary()
    assert canary is not None
    assert canary["genome_id"] == candidate.genome_id
    assert canary["baseline_genome_id"] == env.baseline.genome_id
    assert canary["baseline_hash"] == decision.baseline_hash
    assert canary["stage"] == "canary"
    assert canary["rollback_reason"] is None
    assert canary["circuit_breaker_tripped"] == 0


def test_widened_stop_is_rejected_and_never_reaches_a_gate(env: _Env) -> None:
    wider = _candidate(
        exit_rules=ExitRules(
            regime_invalidation=True,
            r_multiple_min=Decimal("2"),
            stop_atr_multiple=Decimal("2.5"),  # baseline is 1.5
            max_hold_bars=None,
        )
    )
    env.genomes.save_genome(wider, origin="hermes", status="candidate")

    decision = env.controller.evaluate(wider, _dataset(), env.baseline)

    assert decision.promoted is False
    assert "STOP_WIDENED" in decision.rejection_reasons
    assert decision.gate_reports == {}, "a bound violation must short-circuit before the gates"
    assert env.genomes.get_genome_status(wider.genome_id) == "quarantined"
    assert env.promotions.get_open_canary() is None


def test_loosened_data_quality_guard_is_rejected(env: _Env) -> None:
    looser = _candidate(
        guard=GuardBounds(
            min_atr_rate=Decimal("0.0005"),
            max_atr_rate=Decimal("0.015"),
            max_spread_rate=Decimal("0.0040"),  # baseline is 0.0015
        )
    )
    env.genomes.save_genome(looser, origin="hermes", status="candidate")

    decision = env.controller.evaluate(looser, _dataset(), env.baseline)

    assert decision.promoted is False
    assert "SPREAD_GUARD_LOOSENED" in decision.rejection_reasons


def test_unverified_dataset_blocks_promotion(env: _Env) -> None:
    candidate = _candidate()
    env.genomes.save_genome(candidate, origin="hermes", status="candidate")

    decision = env.controller.evaluate(candidate, _dataset(verified=False), env.baseline)

    assert decision.promoted is False
    assert "DATASET_UNVERIFIED" in decision.rejection_reasons
    assert env.genomes.get_genome_status(candidate.genome_id) == "candidate"


def test_revoked_autonomy_blocks_promotion(env: _Env) -> None:
    candidate = _candidate()
    env.genomes.save_genome(candidate, origin="hermes", status="candidate")
    env.autonomy.revoke("operator revoked autonomy during a drawdown")

    decision = env.controller.evaluate(candidate, _dataset(), env.baseline)

    assert decision.promoted is False
    assert "AUTONOMY_REVOKED" in decision.rejection_reasons
    assert env.genomes.get_genome_status(candidate.genome_id) == "candidate"


def test_revoked_autonomy_survives_a_reopened_database(tmp_path) -> None:
    database = Database(tmp_path / "autonomy.db")
    database.migrate()
    AutonomyRepository(database).revoke("operator revoked autonomy")

    reopened = AutonomyRepository(Database(tmp_path / "autonomy.db"))
    assert reopened.is_full_autonomy() is False
    assert reopened.state()["revoked_reason"] == "operator revoked autonomy"

    reopened.restore()
    assert reopened.is_full_autonomy() is True


def test_short_shadow_run_blocks_promotion(env: _Env) -> None:
    candidate = _candidate()
    env.genomes.save_genome(candidate, origin="hermes", status="candidate")
    brief = ShadowEvidence(
        days=3,
        net_pnl=Decimal("1.00"),
        trades=6,
        slippage_acceptable=True,
    )

    decision = env.controller.evaluate(candidate, _dataset(shadow=brief), env.baseline)

    assert decision.promoted is False
    assert "INSUFFICIENT_SHADOW_DURATION" in decision.rejection_reasons
    assert env.promotions.get_open_canary() is None


def test_unbound_shadow_evidence_fails_closed_for_application_dataset(env: _Env) -> None:
    candidate = _candidate()
    env.genomes.save_genome(candidate, origin="hermes", status="candidate")
    dataset = EvidenceDataset(
        dataset_id="app:binance-rest:observed",
        verified=True,
        candles_15m=(),
        shadow=ShadowEvidence(
            days=30,
            net_pnl=Decimal("10"),
            trades=50,
            slippage_acceptable=True,
        ),
    )
    decision = env.controller.evaluate(candidate, dataset, env.baseline)
    assert decision.promoted is False
    assert "SHADOW_EVIDENCE_UNBOUND" in decision.rejection_reasons


def test_holdout_failure_quarantines_the_candidate(tmp_path) -> None:
    environment = _env(tmp_path, holdout=_report(net_return="-0.03"))
    candidate = _candidate()
    environment.genomes.save_genome(candidate, origin="hermes", status="candidate")

    decision = environment.controller.evaluate(candidate, _dataset(), environment.baseline)

    assert decision.promoted is False
    assert "NEGATIVE_HOLDOUT_RETURN" in decision.rejection_reasons
    assert environment.genomes.get_genome_status(candidate.genome_id) == "quarantined"
    assert environment.genomes.get_genome_status(environment.baseline.genome_id) == "active"


def test_evaluate_commit_false_does_not_activate(env: _Env) -> None:
    candidate = _candidate()
    env.genomes.save_genome(candidate, origin="hermes", status="candidate")
    decision = env.controller.evaluate(
        candidate, _dataset(), env.baseline, commit=False
    )
    assert decision.promoted is True
    assert decision.stage == "validated"
    active = env.genomes.get_active_genome()
    assert active is not None and active.genome_id == env.baseline.genome_id


def test_canary_drawdown_rolls_back_to_the_baseline(env: _Env) -> None:
    candidate = _candidate()
    env.genomes.save_genome(candidate, origin="hermes", status="candidate")
    assert env.controller.evaluate(candidate, _dataset(), env.baseline).promoted is True

    rollback = env.controller.on_canary_event(
        CanaryEvent(genome_id=candidate.genome_id, drawdown=Decimal("0.09"), trades=4)
    )

    assert rollback is not None
    assert rollback.restored_genome_id == env.baseline.genome_id
    assert "CANARY_DRAWDOWN_EXCEEDED" in rollback.reason
    assert rollback.circuit_breaker_tripped is True
    assert env.genomes.get_genome_status(candidate.genome_id) == "quarantined"
    restored = env.genomes.get_active_genome()
    assert restored is not None and restored.genome_id == env.baseline.genome_id

    assert env.promotions.get_open_canary() is None
    closed = env.promotions.get_canary(candidate.genome_id)
    assert closed is not None
    assert closed["stage"] == "rolled_back"
    assert closed["rollback_reason"] is not None
    assert closed["circuit_breaker_tripped"] == 1


def test_canary_errors_roll_back_even_while_profitable(env: _Env) -> None:
    candidate = _candidate()
    env.genomes.save_genome(candidate, origin="hermes", status="candidate")
    env.controller.evaluate(candidate, _dataset(), env.baseline)

    rollback = env.controller.on_canary_event(
        CanaryEvent(genome_id=candidate.genome_id, drawdown=Decimal("0"), error_count=3)
    )

    assert rollback is not None
    assert "CANARY_ERROR_BUDGET_EXCEEDED" in rollback.reason


def test_healthy_canary_event_changes_nothing(env: _Env) -> None:
    candidate = _candidate()
    env.genomes.save_genome(candidate, origin="hermes", status="candidate")
    env.controller.evaluate(candidate, _dataset(), env.baseline)

    assert (
        env.controller.on_canary_event(
            CanaryEvent(genome_id=candidate.genome_id, drawdown=Decimal("0.01"), trades=6)
        )
        is None
    )
    assert env.genomes.get_genome_status(candidate.genome_id) == "active"
    canary = env.promotions.get_open_canary()
    assert canary is not None and canary["stage"] == "canary"


def test_canary_event_for_an_unknown_genome_is_ignored(env: _Env) -> None:
    assert (
        env.controller.on_canary_event(
            CanaryEvent(genome_id="never-promoted", drawdown=Decimal("0.99"), error_count=99)
        )
        is None
    )


def test_rollback_is_idempotent(env: _Env) -> None:
    candidate = _candidate()
    env.genomes.save_genome(candidate, origin="hermes", status="candidate")
    env.controller.evaluate(candidate, _dataset(), env.baseline)
    breach = CanaryEvent(genome_id=candidate.genome_id, drawdown=Decimal("0.20"))

    assert env.controller.on_canary_event(breach) is not None
    assert env.controller.on_canary_event(breach) is None, "a closed canary cannot roll back twice"


def test_canary_thresholds_cannot_be_widened_at_runtime() -> None:
    config = CanaryConfig(max_drawdown=Decimal("0.02"), max_errors=1)
    with pytest.raises((AttributeError, TypeError)):
        config.max_drawdown = Decimal("0.50")  # type: ignore[misc]


def test_autonomy_revoked_during_activation_cannot_leave_active_candidate_without_canary(
    tmp_path,
) -> None:
    database = Database(tmp_path / "activation-race.db")
    database.migrate()
    genomes = GenomeRepository(database)
    promotions = PromotionRepository(database)
    autonomy = AutonomyRepository(database)
    pipeline = PromotionPipeline(
        genome_repo=genomes,
        eval_repo=EvaluationRepository(database),
        promotion_repo=promotions,
    )
    baseline = trend_pullback_v1()
    candidate = _candidate(genome_id="race-candidate")
    genomes.save_genome(baseline, origin="baseline", status="active")
    genomes.save_genome(candidate, origin="hermes", status="shadow")

    class RevokingAutonomy(AutonomyRepository):
        def __init__(self, database):
            super().__init__(database)
            self.calls = 0

        def is_full_autonomy(self) -> bool:
            self.calls += 1
            if self.calls >= 3:
                autonomy.revoke("operator revoked during activation")
                return False
            return True

    controller = PromotionController(
        pipeline=pipeline,
        genome_repo=genomes,
        promotion_repo=promotions,
        autonomy_repo=RevokingAutonomy(database),
        engine=_StubEngine(_report()),
        harness=_StubHarness(),
    )

    decision = controller.evaluate(candidate, _dataset(), baseline)

    assert decision.promoted is False
    assert "AUTONOMY_REVOKED" in decision.rejection_reasons
    assert genomes.get_genome_status(candidate.genome_id) == "shadow"
    assert promotions.get_open_canary() is None


def _history_candles(count: int) -> tuple:
    from goldguard.domain.models import Candle

    start = datetime(2026, 1, 1, tzinfo=UTC)
    rows = []
    for index in range(count):
        opened = start + timedelta(minutes=15 * index)
        rows.append(
            Candle(
                symbol="PAXGUSDT",
                timeframe="15m",
                open_time=opened,
                close_time=opened + timedelta(minutes=15) - timedelta(milliseconds=1),
                open=Decimal("2500"),
                high=Decimal("2505"),
                low=Decimal("2495"),
                close=Decimal("2502"),
                volume=Decimal("10"),
                closed=True,
            )
        )
    return tuple(rows)


def test_verified_history_binds_shadow_from_reserved_tail(env: _Env) -> None:
    candidate = _candidate()
    env.genomes.save_genome(candidate, origin="hermes", status="candidate")
    dataset = EvidenceDataset(
        dataset_id="history:PAXGUSDT:verified",
        verified=True,
        candles_15m=_history_candles(14 * 96 + 400),
        shadow=ShadowEvidence(
            days=0,
            net_pnl=Decimal("0"),
            trades=0,
            slippage_acceptable=False,
        ),
    )

    decision = env.controller.evaluate(candidate, dataset, env.baseline)

    assert decision.promoted is True, decision.rejection_reasons
    assert env.genomes.get_genome_status(candidate.genome_id) == "active"
