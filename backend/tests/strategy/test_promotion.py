from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

import pytest
from goldguard.backtest.metrics import PerformanceReport
from goldguard.storage.database import Database
from goldguard.storage.repositories import (
    EvaluationRepository,
    GenomeRepository,
    PromotionRepository,
)
from goldguard.strategy.genome import trend_pullback_v1
from goldguard.strategy.promotion import (
    DevGateConfig,
    PromotionPipeline,
)

START = datetime(2023, 1, 1, tzinfo=UTC)


@pytest.fixture
def database(tmp_path: Path) -> Database:
    db = Database(tmp_path / "goldguard.db")
    db.migrate()
    return db


def test_dev_gate_evaluation_pass_and_fail(database: Database) -> None:
    genome_repo = GenomeRepository(database)
    eval_repo = EvaluationRepository(database)
    prom_repo = PromotionRepository(database)

    pipeline = PromotionPipeline(
        genome_repo=genome_repo,
        eval_repo=eval_repo,
        promotion_repo=prom_repo,
        dev_config=DevGateConfig(
            min_win_rate=Decimal("0.40"),
            min_profit_factor=Decimal("1.20"),
            min_trade_count=5,
        ),
    )

    genome = trend_pullback_v1()
    genome_repo.save_genome(genome, origin="baseline", status="candidate")

    # Failing dev gate (win rate 30%)
    failing_report = PerformanceReport(
        initial_equity=Decimal("100"),
        final_equity=Decimal("105"),
        net_pnl=Decimal("5"),
        gross_pnl=Decimal("6"),
        fee_drag=Decimal("1"),
        net_return=Decimal("0.05"),
        annualized_return=Decimal("0.10"),
        trade_count=10,
        win_rate=Decimal("0.30"),
        profit_factor=Decimal("1.10"),
        expectancy=Decimal("0.5"),
        maximum_drawdown=Decimal("0.05"),
        exposure_rate=Decimal("0.1"),
        sharpe_ratio=Decimal("1.5"),
        sortino_ratio=Decimal("2.0"),
        calmar_ratio=Decimal("2.0"),
        buy_and_hold_return=Decimal("0.02"),
        sample_sufficient=True,
    )
    res_fail = pipeline.evaluate_dev_gate(genome.genome_id, failing_report, run_hash="hash-1")
    assert res_fail.passed is False
    assert "LOW_WIN_RATE" in res_fail.failure_reasons

    # Passing dev gate
    passing_report = PerformanceReport(
        initial_equity=Decimal("100"),
        final_equity=Decimal("120"),
        net_pnl=Decimal("20"),
        gross_pnl=Decimal("22"),
        fee_drag=Decimal("2"),
        net_return=Decimal("0.20"),
        annualized_return=Decimal("0.30"),
        trade_count=10,
        win_rate=Decimal("0.55"),
        profit_factor=Decimal("1.80"),
        expectancy=Decimal("2.0"),
        maximum_drawdown=Decimal("0.04"),
        exposure_rate=Decimal("0.1"),
        sharpe_ratio=Decimal("2.1"),
        sortino_ratio=Decimal("3.0"),
        calmar_ratio=Decimal("5.0"),
        buy_and_hold_return=Decimal("0.02"),
        sample_sufficient=True,
    )
    res_pass = pipeline.evaluate_dev_gate(genome.genome_id, passing_report, run_hash="hash-2")
    assert res_pass.passed is True
    assert genome_repo.get_genome_status(genome.genome_id) == "dev_passed"


def test_holdout_failure_quarantines_genome_permanently(database: Database) -> None:
    genome_repo = GenomeRepository(database)
    eval_repo = EvaluationRepository(database)
    prom_repo = PromotionRepository(database)

    pipeline = PromotionPipeline(
        genome_repo=genome_repo,
        eval_repo=eval_repo,
        promotion_repo=prom_repo,
    )

    genome = trend_pullback_v1()
    genome_repo.save_genome(genome, origin="baseline", status="val_passed")

    # Simulate holdout failure with max_drawdown > 0.15
    failing_holdout_report = PerformanceReport(
        initial_equity=Decimal("100"),
        final_equity=Decimal("80"),
        net_pnl=Decimal("-20"),
        gross_pnl=Decimal("-18"),
        fee_drag=Decimal("2"),
        net_return=Decimal("-0.20"),
        annualized_return=Decimal("-0.30"),
        trade_count=10,
        win_rate=Decimal("0.20"),
        profit_factor=Decimal("0.50"),
        expectancy=Decimal("-2.0"),
        maximum_drawdown=Decimal("0.25"),
        exposure_rate=Decimal("0.1"),
        sharpe_ratio=Decimal("-1.0"),
        sortino_ratio=Decimal("-1.0"),
        calmar_ratio=None,
        buy_and_hold_return=Decimal("0.01"),
        sample_sufficient=True,
    )

    gate_res = pipeline.evaluate_holdout_gate(
        genome=genome,
        holdout_report=failing_holdout_report,
        run_hash="holdout-fail-hash",
    )

    assert gate_res.passed is False
    # Verified permanent quarantine in DB
    status = genome_repo.get_genome_status(genome.genome_id)
    assert status == "quarantined"


def test_promotion_churn_prevention(database: Database) -> None:
    genome_repo = GenomeRepository(database)
    eval_repo = EvaluationRepository(database)
    prom_repo = PromotionRepository(database)

    pipeline = PromotionPipeline(
        genome_repo=genome_repo,
        eval_repo=eval_repo,
        promotion_repo=prom_repo,
    )

    genome1 = trend_pullback_v1()
    genome_repo.save_genome(genome1, origin="baseline", status="shadow")

    old_genome = trend_pullback_v1().model_copy(update={"genome_id": "old-genome"})
    genome_repo.save_genome(old_genome, origin="baseline", status="active")

    # Record a promotion 2 hours ago
    prom_repo.record_promotion(
        promotion_id="prev-prom-1",
        genome_id="old-genome",
        promoted_by="hermes_autonomy",
        mode="active",
        gate_report={"status": "ok"},
    )

    # Attempting to promote another strategy within 24 hours fails due to churn
    can_promote, reason = pipeline.can_promote_to_active(full_autonomy=True)
    assert can_promote is False
    assert reason == "PROMOTION_CHURN_HALT"
