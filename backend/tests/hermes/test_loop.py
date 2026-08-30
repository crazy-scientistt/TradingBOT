import json
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path

import httpx
import pytest
from goldguard.backtest.engine import BacktestEngine, BacktestResult
from goldguard.backtest.metrics import PerformanceReport
from goldguard.backtest.walk_forward import WalkForwardHarness, WalkForwardReport
from goldguard.domain.models import Candle
from goldguard.hermes.client import HermesClient
from goldguard.hermes.generator import StrategyProposalGenerator
from goldguard.hermes.loop import HermesLoopConfig, HermesResearchLoop
from goldguard.memory.engine import MemoryBank
from goldguard.providers.client import GatewayClient
from goldguard.services.promotion_controller import (
    EvidenceDataset,
    PromotionController,
    PromotionDecision,
    ShadowEvidence,
)
from goldguard.storage.database import Database
from goldguard.storage.repositories import (
    AutonomyRepository,
    EvaluationRepository,
    GenomeRepository,
    PromotionRepository,
    QuotaRepository,
    ReflectionRepository,
)
from goldguard.strategy.genome import StrategyGenome, trend_pullback_v1
from goldguard.strategy.promotion import PromotionPipeline

START = datetime(2023, 1, 1, tzinfo=UTC)


@pytest.fixture
def database(tmp_path: Path) -> Database:
    db = Database(tmp_path / "goldguard.db")
    db.migrate()
    return db


def generate_market_data(num_days: int = 15) -> list[Candle]:
    candles: list[Candle] = []
    curr = START
    base_price = Decimal("2000")
    for i in range(num_days * 30):
        cycle = Decimal(str((i % 30) - 15)) / Decimal("10")
        close_p = base_price + Decimal(str(i // 30)) + cycle
        c = Candle(
            symbol="PAXGUSDT",
            timeframe="15m",
            open_time=curr,
            close_time=curr + timedelta(minutes=15) - timedelta(milliseconds=1),
            open=close_p - Decimal("1"),
            high=close_p + Decimal("3"),
            low=close_p - Decimal("3"),
            close=close_p,
            volume=Decimal("15"),
            closed=True,
        )
        candles.append(c)
        curr += timedelta(minutes=15)
    return candles


@pytest.mark.asyncio
async def test_hermes_research_loop_quota_exhaustion_blocks_iteration(
    database: Database,
) -> None:
    genome_repo = GenomeRepository(database)
    eval_repo = EvaluationRepository(database)
    prom_repo = PromotionRepository(database)
    quota_repo = QuotaRepository(database)
    refl_repo = ReflectionRepository(database)
    mem_bank = MemoryBank(refl_repo)

    pipeline = PromotionPipeline(
        genome_repo=genome_repo,
        eval_repo=eval_repo,
        promotion_repo=prom_repo,
    )

    async def mock_handler(req: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={})

    transport = httpx.MockTransport(mock_handler)
    async with httpx.AsyncClient(transport=transport) as http_client:
        gateway = GatewayClient(base_url="http://localhost:10100", http_client=http_client)
        generator = StrategyProposalGenerator(
            hermes_client=HermesClient(
                base_url="http://hermes.test",
                api_key="test-key",
                http_client=http_client,
            )
        )

        loop = HermesResearchLoop(
            proposal_generator=generator,
            backtest_engine=BacktestEngine(),
            wf_harness=WalkForwardHarness(),
            promotion_pipeline=pipeline,
            genome_repo=genome_repo,
            quota_repo=quota_repo,
            memory_bank=mem_bank,
            config=HermesLoopConfig(max_backtest_calls=1),
        )

        candles = generate_market_data(num_days=10)
        now = datetime(2026, 8, 26, 12, tzinfo=UTC)

        # 1. First iteration consumes the 1 allowed call
        quota_repo.consume_backtest("2026-08-26", max_limit=1)

        # 2. Next step attempt must return quota_exhausted
        result = await loop.step(
            candles_15m=candles,
            market_summary="Normal volatility",
            now=now,
        )
        assert result.status == "quota_exhausted"


@pytest.mark.asyncio
async def test_hermes_research_loop_successful_proposal_flow(database: Database) -> None:
    genome_repo = GenomeRepository(database)
    eval_repo = EvaluationRepository(database)
    prom_repo = PromotionRepository(database)
    quota_repo = QuotaRepository(database)
    refl_repo = ReflectionRepository(database)
    mem_bank = MemoryBank(refl_repo)

    # Set up baseline active genome
    active_genome = trend_pullback_v1()
    genome_repo.save_genome(active_genome, origin="baseline", status="active")

    pipeline = PromotionPipeline(
        genome_repo=genome_repo,
        eval_repo=eval_repo,
        promotion_repo=prom_repo,
    )

    valid_proposal = {
        "hypothesis": "Adjust volume ratio threshold to filter noise.",
        "evidence_refs": ["ref-1"],
        "parameter_changes": {
            "minimum_volume_ratio": "0.85",
        },
    }

    async def mock_handler(req: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "id": "chat-loop-1",
                "model": "google-antigravity/gemini-3.7-flash",
                "choices": [
                    {
                        "index": 0,
                        "message": {"role": "assistant", "content": json.dumps(valid_proposal)},
                    }
                ],
            },
        )

    transport = httpx.MockTransport(mock_handler)
    async with httpx.AsyncClient(transport=transport) as http_client:
        gateway = GatewayClient(base_url="http://localhost:10100", http_client=http_client)
        generator = StrategyProposalGenerator(
            hermes_client=HermesClient(
                base_url="http://hermes.test",
                api_key="test-key",
                http_client=http_client,
            )
        )

        loop = HermesResearchLoop(
            proposal_generator=generator,
            backtest_engine=BacktestEngine(),
            wf_harness=WalkForwardHarness(),
            promotion_pipeline=pipeline,
            genome_repo=genome_repo,
            quota_repo=quota_repo,
            memory_bank=mem_bank,
            config=HermesLoopConfig(max_backtest_calls=10),
        )

        candles = generate_market_data(num_days=10)
        now = datetime(2026, 8, 26, 12, tzinfo=UTC)

        result = await loop.step(
            candles_15m=candles,
            market_summary="Normal volatility",
            now=now,
        )

        assert result.status in ("promoted_candidate", "dev_failed", "val_failed")
        assert result.candidate_genome_id is not None
        # Assert evaluation row written to database
        evals = eval_repo.get_evaluations_for_genome(result.candidate_genome_id)
        assert len(evals) >= 1


def _gateway_returning(proposal: dict) -> httpx.MockTransport:
    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "id": "chat-loop-autonomy",
                "model": "google-antigravity/gemini-3.7-flash",
                "choices": [
                    {
                        "index": 0,
                        "message": {"role": "assistant", "content": json.dumps(proposal)},
                    }
                ],
            },
        )

    return httpx.MockTransport(handler)


VALID_PROPOSAL = {
    "hypothesis": "Adjust volume ratio threshold to filter noise.",
    "evidence_refs": ["ref-1"],
    "parameter_changes": {"minimum_volume_ratio": "0.85"},
}


def _passing_report() -> PerformanceReport:
    """A report that clears the loop's development and validation screens."""
    return PerformanceReport(
        initial_equity=Decimal("100"),
        final_equity=Decimal("108"),
        net_pnl=Decimal("8"),
        gross_pnl=Decimal("9"),
        fee_drag=Decimal("1"),
        net_return=Decimal("0.08"),
        annualized_return=None,
        trade_count=40,
        win_rate=Decimal("0.55"),
        profit_factor=Decimal("1.80"),
        expectancy=Decimal("0.2"),
        maximum_drawdown=Decimal("0.04"),
        exposure_rate=Decimal("0.3"),
        sharpe_ratio=Decimal("1.1"),
        sortino_ratio=Decimal("1.4"),
        calmar_ratio=Decimal("2.0"),
        buy_and_hold_return=Decimal("0.02"),
        sample_sufficient=True,
    )


class _StubEngine:
    """Stands in for the backtest so the screen sees a decided report, not synthetic noise."""

    def run(self, genome: StrategyGenome, candles_15m: object, *args: object, **kwargs: object):
        return BacktestResult(
            trades=(),
            report=_passing_report(),
            equity_curve=(),
            run_hash="stub-run-hash",
            metrics_dict={},
            mae=Decimal("0"),
            mfe=Decimal("0"),
            ulcer_index=Decimal("0"),
        )


class _StubHarness:
    """Stands in for walk-forward so the loop reaches the promotion handoff."""

    def evaluate(
        self,
        *,
        genome: StrategyGenome,
        candles_15m: object,
        windows: object = None,
        unlock_holdout: bool = False,
        promotion_token: str | None = None,
    ) -> WalkForwardReport:
        return WalkForwardReport(
            genome_id=genome.genome_id,
            windows=(),
            aggregate_in_sample_return=Decimal("0.10"),
            aggregate_out_of_sample_return=Decimal("0.08"),
            wfe=Decimal("0.80"),
            deflated_sharpe_ratio=Decimal("0.99"),
            pbo=Decimal("0.20"),
            max_out_of_sample_drawdown=Decimal("0.05"),
            gate_passed=True,
            gate_failure_reasons=(),
            holdout_evaluated=False,
            holdout_result=None,
        )


def _loop(
    database: Database,
    *,
    http_client: httpx.AsyncClient,
    controller: PromotionController | None = None,
    engine: object | None = None,
    harness: object | None = None,
    max_backtests: int = 10,
    autopromotion_enabled: bool = False,
) -> HermesResearchLoop:
    genome_repo = GenomeRepository(database)
    if genome_repo.get_active_genome() is None:
        genome_repo.save_genome(trend_pullback_v1(), origin="baseline", status="active")
    gateway = GatewayClient(base_url="http://localhost:10100", http_client=http_client)
    return HermesResearchLoop(
        proposal_generator=StrategyProposalGenerator(
            hermes_client=HermesClient(
                base_url="http://hermes.test",
                api_key="test-key",
                http_client=http_client,
            )
        ),
        backtest_engine=engine or BacktestEngine(),  # type: ignore[arg-type]
        wf_harness=harness or WalkForwardHarness(),  # type: ignore[arg-type]
        promotion_pipeline=PromotionPipeline(
            genome_repo=genome_repo,
            eval_repo=EvaluationRepository(database),
            promotion_repo=PromotionRepository(database),
        ),
        genome_repo=genome_repo,
        quota_repo=QuotaRepository(database),
        memory_bank=MemoryBank(ReflectionRepository(database)),
        autonomy_repo=AutonomyRepository(database),
        promotion_controller=controller,
        config=HermesLoopConfig(
            max_backtest_calls=max_backtests,
            autopromotion_enabled=autopromotion_enabled,
        ),
    )


@pytest.mark.asyncio
async def test_revoked_autonomy_stops_the_loop_before_it_mutates_anything(
    database: Database,
) -> None:
    """Revoking autonomy must block research mutation, not merely warn about it."""
    quota_repo = QuotaRepository(database)
    AutonomyRepository(database).revoke("operator halted research")

    transport = _gateway_returning(VALID_PROPOSAL)
    async with httpx.AsyncClient(transport=transport) as http_client:
        loop = _loop(database, http_client=http_client)
        result = await loop.step(
            candles_15m=generate_market_data(num_days=10),
            now=datetime(2026, 8, 26, 12, tzinfo=UTC),
        )

    assert result.status == "autonomy_revoked"
    assert result.candidate_genome_id is None
    assert GenomeRepository(database).list_genomes(status="candidate") == []
    # A blocked loop must not spend the day's research budget either.
    assert quota_repo.get_usage("2026-08-26") == (0, 0)


@pytest.mark.asyncio
async def test_a_passing_candidate_is_handed_to_the_promotion_controller(
    database: Database,
) -> None:
    """The loop stops at 'proposed'; only the controller may promote."""
    recorded: list[str] = []

    class RecordingController:
        def evaluate(self, candidate, dataset, baseline):  # type: ignore[no-untyped-def]
            recorded.append(candidate.genome_id)
            return PromotionDecision(
                promoted=True,
                stage="canary",
                candidate_id=candidate.genome_id,
                candidate_hash="candidate-hash",
                baseline_id=baseline.genome_id,
                baseline_hash="baseline-hash",
                dataset_id=dataset.dataset_id,
                detail="all gates passed",
                promoted_by="promotion_controller",
                promotion_id="prom-1",
            )

    candles = generate_market_data(num_days=10)
    dataset = EvidenceDataset(
        dataset_id="paxg-3y-15m",
        verified=True,
        candles_15m=tuple(candles),
        shadow=ShadowEvidence(
            days=21,
            net_pnl=Decimal("2.50"),
            trades=9,
            slippage_acceptable=True,
        ),
    )

    transport = _gateway_returning(VALID_PROPOSAL)
    async with httpx.AsyncClient(transport=transport) as http_client:
        loop = _loop(
            database,
            http_client=http_client,
            controller=RecordingController(),
            engine=_StubEngine(),
            harness=_StubHarness(),
        )
        result = await loop.step(
            candles_15m=candles,
            dataset=dataset,
            now=datetime(2026, 8, 26, 12, tzinfo=UTC),
        )

    assert result.status == "promotion_held"
    assert result.candidate_genome_id is not None
    assert recorded == [result.candidate_genome_id], "the controller must judge the candidate"
    assert "autopromotion_enabled is false" in result.gate_results["reason"]


@pytest.mark.asyncio
async def test_autopromotion_flag_is_required_to_activate_a_candidate(
    database: Database,
) -> None:
    class Approve:
        def evaluate(self, candidate, dataset, baseline):  # type: ignore[no-untyped-def]
            return PromotionDecision(
                promoted=True,
                stage="canary",
                candidate_id=candidate.genome_id,
                candidate_hash="candidate-hash",
                baseline_id=baseline.genome_id,
                baseline_hash="baseline-hash",
                dataset_id=dataset.dataset_id,
                detail="all gates passed",
                promoted_by="promotion_controller",
                promotion_id="prom-1",
            )

    candles = generate_market_data(num_days=10)
    dataset = EvidenceDataset(
        dataset_id="paxg-3y-15m",
        verified=True,
        candles_15m=tuple(candles),
        shadow=ShadowEvidence(days=21, net_pnl=Decimal("2.50"), trades=9, slippage_acceptable=True),
    )
    transport = _gateway_returning(VALID_PROPOSAL)
    async with httpx.AsyncClient(transport=transport) as http_client:
        loop = _loop(
            database,
            http_client=http_client,
            controller=Approve(),
            engine=_StubEngine(),
            harness=_StubHarness(),
            autopromotion_enabled=True,
        )
        result = await loop.step(
            candles_15m=candles,
            dataset=dataset,
            now=datetime(2026, 8, 26, 12, tzinfo=UTC),
        )
    assert result.status == "promoted"


@pytest.mark.asyncio
async def test_a_rejected_candidate_is_reported_not_promoted(database: Database) -> None:
    class RejectingController:
        def evaluate(self, candidate, dataset, baseline):  # type: ignore[no-untyped-def]
            return PromotionDecision(
                promoted=False,
                stage="quarantined",
                candidate_id=candidate.genome_id,
                candidate_hash="candidate-hash",
                baseline_id=baseline.genome_id,
                baseline_hash="baseline-hash",
                dataset_id=dataset.dataset_id,
                detail="candidate loosens a protective bound and was quarantined",
                rejection_reasons=("STOP_WIDENED",),
            )

    candles = generate_market_data(num_days=10)
    dataset = EvidenceDataset(
        dataset_id="paxg-3y-15m",
        verified=True,
        candles_15m=tuple(candles),
        shadow=ShadowEvidence(
            days=21,
            net_pnl=Decimal("2.50"),
            trades=9,
            slippage_acceptable=True,
        ),
    )

    transport = _gateway_returning(VALID_PROPOSAL)
    async with httpx.AsyncClient(transport=transport) as http_client:
        loop = _loop(
            database,
            http_client=http_client,
            controller=RejectingController(),
            engine=_StubEngine(),
            harness=_StubHarness(),
        )
        result = await loop.step(
            candles_15m=candles,
            dataset=dataset,
            now=datetime(2026, 8, 26, 12, tzinfo=UTC),
        )

    assert result.status == "promotion_rejected"
    assert result.gate_results["reasons"] == ["STOP_WIDENED"]


@pytest.mark.asyncio
async def test_autonomy_revoked_during_proposal_prevents_candidate_persistence(
    database: Database,
) -> None:
    autonomy = AutonomyRepository(database)

    class RevokingGenerator:
        async def propose(self, **kwargs):  # type: ignore[no-untyped-def]
            autonomy.revoke("operator revoked while Hermes was thinking")
            return trend_pullback_v1().model_copy(update={"genome_id": "race-candidate"})

    loop = _loop(database, http_client=httpx.AsyncClient())
    loop.proposal_generator = RevokingGenerator()  # type: ignore[assignment]
    result = await loop.step(candles_15m=generate_market_data(num_days=10))
    assert result.status == "autonomy_revoked"
    assert GenomeRepository(database).get_genome("race-candidate") is None


@pytest.mark.asyncio
async def test_hermes_validation_failure_reports_quota_after_evaluation(database: Database) -> None:
    """A quota-consuming validation evaluation must be reflected in the result."""
    candles = generate_market_data(num_days=10)
    transport = _gateway_returning(VALID_PROPOSAL)

    class ValidationFailHarness(_StubHarness):
        def evaluate(self, **kwargs):  # type: ignore[no-untyped-def]
            report = super().evaluate(**kwargs)
            return report.__class__(
                **{
                    **report.__dict__,
                    "wfe": Decimal("0.10"),
                }
            )

    async with httpx.AsyncClient(transport=transport) as http_client:
        loop = _loop(
            database,
            http_client=http_client,
            engine=_StubEngine(),
            harness=ValidationFailHarness(),
            max_backtests=10,
        )
        result = await loop.step(
            candles_15m=candles,
            now=datetime(2026, 8, 26, 12, tzinfo=UTC),
        )

    assert result.status == "val_failed"
    assert QuotaRepository(database).get_usage("2026-08-26") == (2, 0)
    assert result.quota_used == (2, 0)
