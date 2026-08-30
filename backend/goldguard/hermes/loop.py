from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, Protocol
from uuid import uuid4

from goldguard.backtest.engine import BacktestEngine
from goldguard.backtest.walk_forward import WalkForwardHarness
from goldguard.domain.models import Candle
from goldguard.hermes.generator import (
    ProposalValidationError,
    StrategyProposalGenerator,
)
from goldguard.memory.engine import MemoryBank
from goldguard.services.promotion_controller import EvidenceDataset, PromotionDecision
from goldguard.storage.repositories import (
    AutonomyRepository,
    GenomeRepository,
    QuotaRepository,
)
from goldguard.strategy.genome import StrategyGenome, trend_pullback_v1
from goldguard.strategy.promotion import PromotionPipeline


class PromotionJudge(Protocol):
    def evaluate(
        self,
        candidate: StrategyGenome,
        dataset: EvidenceDataset,
        baseline: StrategyGenome,
    ) -> PromotionDecision: ...


@dataclass(frozen=True)
class HermesLoopConfig:
    max_iterations_per_day: int = 10
    max_backtest_calls: int = 50
    max_web_calls: int = 20
    consecutive_failure_limit: int = 3
    autopromotion_enabled: bool = False


@dataclass(frozen=True)
class LoopIterationResult:
    iteration_id: str
    status: str
    candidate_genome_id: str | None = None
    gate_results: dict[str, Any] = field(default_factory=dict)
    quota_used: tuple[int, int] = (0, 0)
    circuit_breaker_tripped: bool = False


class HermesResearchLoop:
    """Autonomous quantitative strategy research loop with strict budget and circuit breakers."""

    def __init__(
        self,
        *,
        proposal_generator: StrategyProposalGenerator,
        backtest_engine: BacktestEngine,
        wf_harness: WalkForwardHarness,
        promotion_pipeline: PromotionPipeline,
        genome_repo: GenomeRepository,
        quota_repo: QuotaRepository,
        memory_bank: MemoryBank,
        autonomy_repo: AutonomyRepository | None = None,
        promotion_controller: PromotionJudge | None = None,
        config: HermesLoopConfig | None = None,
    ) -> None:
        self.proposal_generator = proposal_generator
        self.backtest_engine = backtest_engine
        self.wf_harness = wf_harness
        self.promotion_pipeline = promotion_pipeline
        self.genome_repo = genome_repo
        self.quota_repo = quota_repo
        self.memory_bank = memory_bank
        self.autonomy_repo = autonomy_repo
        self.promotion_controller = promotion_controller
        self.config = config or HermesLoopConfig()
        self.consecutive_failures = 0
        self._steps_date = ""
        self._steps_today = 0

    async def step(
        self,
        *,
        candles_15m: Sequence[Candle],
        market_summary: str = "",
        dataset: EvidenceDataset | None = None,
        now: datetime | None = None,
    ) -> LoopIterationResult:
        current_time = now or datetime.now(UTC)
        date_str = current_time.strftime("%Y-%m-%d")
        iteration_id = f"hermes-loop-{uuid4().hex[:8]}"

        # 0. Autonomy kill switch. Checked before the quota so a revoked bot spends nothing.
        if self.autonomy_repo is not None and not self.autonomy_repo.is_full_autonomy():
            state = self.autonomy_repo.state()
            return LoopIterationResult(
                iteration_id=iteration_id,
                status="autonomy_revoked",
                quota_used=self.quota_repo.get_usage(date_str),
                gate_results={"reason": state["revoked_reason"] or "autonomy is revoked"},
            )

        if self._steps_date != date_str:
            self._steps_date = date_str
            self._steps_today = 0
        if self._steps_today >= self.config.max_iterations_per_day:
            return LoopIterationResult(
                iteration_id=iteration_id,
                status="quota_exhausted",
                quota_used=self.quota_repo.get_usage(date_str),
                gate_results={"reason": "daily hermes iteration cap reached"},
            )
        if self._is_circuit_breaker_tripped():
            return LoopIterationResult(
                iteration_id=iteration_id,
                status="circuit_open",
                quota_used=self.quota_repo.get_usage(date_str),
                circuit_breaker_tripped=True,
            )
        self._steps_today += 1

        # 1. Budget and Quota check
        usage = self.quota_repo.get_usage(date_str)
        if usage[0] >= self.config.max_backtest_calls:
            return LoopIterationResult(
                iteration_id=iteration_id,
                status="quota_exhausted",
                quota_used=self.quota_repo.get_usage(date_str),
            )

        # 2. Identify parent genome & pull reflections
        parent = self.genome_repo.get_active_genome() or trend_pullback_v1()
        reflections = self.memory_bank.query_relevant_summaries(
            namespace="forward",
            limit=10,
        )

        # 3. Request bounded proposal from Hermes LLM
        try:
            candidate_genome = await self.proposal_generator.propose(
                parent_genome=parent,
                reflections=reflections,
                market_summary=market_summary,
            )
        except (ProposalValidationError, Exception) as exc:
            self._record_failure()
            return LoopIterationResult(
                iteration_id=iteration_id,
                status="proposal_rejected",
                quota_used=self.quota_repo.get_usage(date_str),
                circuit_breaker_tripped=self._is_circuit_breaker_tripped(),
                gate_results={"error": str(exc)},
            )

        # Autonomy may be revoked while the awaited proposal call is in flight.
        # Re-check before any durable candidate mutation.
        if self.autonomy_repo is not None and not self.autonomy_repo.is_full_autonomy():
            state = self.autonomy_repo.state()
            return LoopIterationResult(
                iteration_id=iteration_id,
                status="autonomy_revoked",
                quota_used=self.quota_repo.get_usage(date_str),
                gate_results={"reason": state["revoked_reason"] or "autonomy is revoked"},
            )

        if self.promotion_controller is not None and dataset is not None:
            if not dataset.verified:
                return LoopIterationResult(
                    iteration_id=iteration_id,
                    status="dataset_unverified",
                    quota_used=self.quota_repo.get_usage(date_str),
                    gate_results={"reason": "CORRUPT or unverified dataset cannot qualify Hermes"},
                )
            set_budget = getattr(self.promotion_controller, "set_backtest_budget", None)
            if callable(set_budget):
                set_budget(
                    lambda: self.quota_repo.consume_backtest(
                        date_str=date_str, max_limit=self.config.max_backtest_calls
                    )
                )
            self.genome_repo.save_genome(candidate_genome, origin="hermes", status="candidate")
            cand_id = candidate_genome.genome_id
            decision = self.promotion_controller.evaluate(candidate_genome, dataset, parent)
            fresh_usage = self.quota_repo.get_usage(date_str)
            if not decision.promoted:
                self._record_failure()
                return LoopIterationResult(
                    iteration_id=iteration_id,
                    status="promotion_rejected",
                    candidate_genome_id=cand_id,
                    gate_results={
                        **decision.gate_reports,
                        "reasons": list(decision.rejection_reasons),
                    },
                    quota_used=fresh_usage,
                    circuit_breaker_tripped=self._is_circuit_breaker_tripped(),
                )
            if not self.config.autopromotion_enabled:
                return LoopIterationResult(
                    iteration_id=iteration_id,
                    status="promotion_held",
                    candidate_genome_id=cand_id,
                    gate_results={
                        **decision.gate_reports,
                        "reason": "autopromotion_enabled is false",
                    },
                    quota_used=fresh_usage,
                )
            self.consecutive_failures = 0
            return LoopIterationResult(
                iteration_id=iteration_id,
                status="promoted",
                candidate_genome_id=cand_id,
                gate_results={
                    **decision.gate_reports,
                    "promoted_by": decision.promoted_by,
                    "promotion_id": decision.promotion_id,
                    "stage": decision.stage,
                },
                quota_used=fresh_usage,
                circuit_breaker_tripped=False,
            )

        # 4. Persist candidate in repository
        self.genome_repo.save_genome(candidate_genome, origin="hermes", status="candidate")
        cand_id = candidate_genome.genome_id

        # 5. Evaluate Development Gate
        dev_end = len(candles_15m) * 70 // 100
        dev_candles = candles_15m[: max(dev_end, 30)]

        if not self.quota_repo.consume_backtest(
            date_str=date_str, max_limit=self.config.max_backtest_calls
        ):
            return LoopIterationResult(
                iteration_id=iteration_id,
                status="quota_exhausted",
                candidate_genome_id=cand_id,
                quota_used=self.quota_repo.get_usage(date_str),
            )
        dev_bt = self.backtest_engine.run(candidate_genome, dev_candles)
        dev_res = self.promotion_pipeline.evaluate_dev_gate(
            genome_id=cand_id,
            report=dev_bt.report,
            run_hash=dev_bt.run_hash,
        )
        if not dev_res.passed:
            self._record_failure()
            return LoopIterationResult(
                iteration_id=iteration_id,
                status="dev_failed",
                candidate_genome_id=cand_id,
                gate_results={"development": dev_res.metrics, "reasons": dev_res.failure_reasons},
                quota_used=self.quota_repo.get_usage(date_str),
                circuit_breaker_tripped=self._is_circuit_breaker_tripped(),
            )

        # 6. Evaluate Validation Gate
        val_end = dev_end + (len(candles_15m) * 15 // 100)
        active_candles = candles_15m[: max(val_end, 50)]

        if not self.quota_repo.consume_backtest(
            date_str=date_str, max_limit=self.config.max_backtest_calls
        ):
            return LoopIterationResult(
                iteration_id=iteration_id,
                status="quota_exhausted",
                candidate_genome_id=cand_id,
                quota_used=self.quota_repo.get_usage(date_str),
            )
        wf_report = self.wf_harness.evaluate(
            genome=candidate_genome,
            candles_15m=active_candles,
            unlock_holdout=False,
        )
        val_res = self.promotion_pipeline.evaluate_val_gate(
            genome_id=cand_id,
            wf_report=wf_report,
            run_hash=f"wf-{cand_id}",
        )
        if not val_res.passed:
            self._record_failure()
            return LoopIterationResult(
                iteration_id=iteration_id,
                status="val_failed",
                candidate_genome_id=cand_id,
                gate_results={
                    "development": dev_res.metrics,
                    "validation": val_res.metrics,
                    "reasons": val_res.failure_reasons,
                },
                quota_used=self.quota_repo.get_usage(date_str),
                circuit_breaker_tripped=self._is_circuit_breaker_tripped(),
            )

        # Success on the screening gates. The loop itself may never promote: when a
        # controller is attached it is the sole authority, re-running the full gate
        # sequence (including the sealed holdout) and opening the canary.
        # ponytail: with a controller attached the dev/validation backtests run twice per
        # candidate — once here, once inside the controller. Promotion runs at most once a
        # day, so pass the screening results through if that ever stops being true.
        # Success: reset consecutive failures
        self.consecutive_failures = 0
        return LoopIterationResult(
            iteration_id=iteration_id,
            status="promoted_candidate",
            candidate_genome_id=cand_id,
            gate_results={"development": dev_res.metrics, "validation": val_res.metrics},
            quota_used=self.quota_repo.get_usage(date_str),
            circuit_breaker_tripped=False,
        )

    def _record_failure(self) -> None:
        self.consecutive_failures += 1

    def _is_circuit_breaker_tripped(self) -> bool:
        return self.consecutive_failures >= self.config.consecutive_failure_limit
