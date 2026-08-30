"""Autonomous promotion and rollback.

The controller is the only thing that promotes a strategy. It runs the four existing
gates in order, refuses any candidate that loosens a protective bound, opens a durable
canary record on promotion, and reverts to the baseline on its own when the canary
misbehaves. No human approval is involved in the routine path, and no path here can
widen a stop, loosen a data-quality guard, or promote past a failed gate.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from decimal import Decimal
from typing import TYPE_CHECKING, Any, Protocol
from uuid import uuid4

from goldguard.backtest.metrics import PerformanceReport
from goldguard.domain.models import Candle
from goldguard.strategy.genome import StrategyGenome, genome_hash
from goldguard.strategy.promotion import GateResult, PromotionPipeline

if TYPE_CHECKING:
    from goldguard.backtest.walk_forward import WalkForwardReport
    from goldguard.storage.repositories import (
        AutonomyRepository,
        GenomeRepository,
        PromotionRepository,
    )


class BacktestRunner(Protocol):
    def run(
        self,
        genome: StrategyGenome,
        candles_15m: Sequence[Candle],
        *args: Any,
        **kwargs: Any,
    ) -> Any: ...


class WalkForwardRunner(Protocol):
    def evaluate(
        self,
        *,
        genome: StrategyGenome,
        candles_15m: Sequence[Candle],
        unlock_holdout: bool = False,
        promotion_token: str | None = None,
    ) -> WalkForwardReport: ...


@dataclass(frozen=True)
class ShadowEvidence:
    """Measured paper-trading history for the candidate. Never estimated."""

    days: int
    net_pnl: Decimal
    trades: int
    slippage_acceptable: bool
    candidate_id: str | None = None


@dataclass(frozen=True)
class EvidenceDataset:
    """The verified series the gates judge against, plus its identity."""

    dataset_id: str
    verified: bool
    candles_15m: tuple[Candle, ...]
    shadow: ShadowEvidence


@dataclass(frozen=True)
class PromotionDecision:
    promoted: bool
    stage: str
    candidate_id: str
    candidate_hash: str
    baseline_id: str
    baseline_hash: str
    dataset_id: str
    detail: str
    promoted_by: str | None = None
    promotion_id: str | None = None
    rejection_reasons: tuple[str, ...] = ()
    gate_reports: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class CanaryEvent:
    """One observation of a promoted candidate running live on paper."""

    genome_id: str
    drawdown: Decimal
    error_count: int = 0
    trades: int = 0


@dataclass(frozen=True)
class RollbackDecision:
    genome_id: str
    restored_genome_id: str | None
    reason: str
    circuit_breaker_tripped: bool


@dataclass(frozen=True)
class CanaryConfig:
    max_drawdown: Decimal = Decimal("0.05")
    max_errors: int = 3


PROMOTED_BY = "promotion_controller"
SHADOW_WINDOW_BARS_15M = 14 * 24 * 4  # 14 days of 15-minute closes


class PromotionController:
    def __init__(
        self,
        *,
        pipeline: PromotionPipeline,
        genome_repo: GenomeRepository,
        promotion_repo: PromotionRepository,
        autonomy_repo: AutonomyRepository,
        engine: BacktestRunner,
        harness: WalkForwardRunner,
        canary_config: CanaryConfig | None = None,
    ) -> None:
        self._pipeline = pipeline
        self._genomes = genome_repo
        self._promotions = promotion_repo
        self._autonomy = autonomy_repo
        self._engine = engine
        self._harness = harness
        self._canary = canary_config or CanaryConfig()
        self._backtest_budget: Callable[[], bool] | None = None

    def set_backtest_budget(self, callback: Callable[[], bool] | None) -> None:
        self._backtest_budget = callback

    def _consume_backtest(self) -> None:
        if self._backtest_budget is not None and not self._backtest_budget():
            raise RuntimeError("backtest quota exhausted")

    # -- promotion -----------------------------------------------------------------

    def evaluate(
        self,
        candidate: StrategyGenome,
        dataset: EvidenceDataset,
        baseline: StrategyGenome,
        *,
        commit: bool = True,
    ) -> PromotionDecision:
        candidate_hash = genome_hash(candidate)
        baseline_hash = genome_hash(baseline)

        def reject(
            reasons: Sequence[str],
            detail: str,
            *,
            stage: str = "candidate",
            gate_reports: dict[str, Any] | None = None,
        ) -> PromotionDecision:
            return PromotionDecision(
                promoted=False,
                stage=stage,
                candidate_id=candidate.genome_id,
                candidate_hash=candidate_hash,
                baseline_id=baseline.genome_id,
                baseline_hash=baseline_hash,
                dataset_id=dataset.dataset_id,
                detail=detail,
                rejection_reasons=tuple(reasons),
                gate_reports=gate_reports or {},
            )

        # A candidate that loosens a bound is not a weak candidate, it is out of contract:
        # short-circuit before any gate so a persuasive backtest cannot argue for it.
        violations = risk_bound_violations(candidate, baseline)
        if violations:
            self._genomes.update_status(candidate.genome_id, "quarantined")
            return reject(
                violations,
                "candidate loosens a protective bound and was quarantined",
                stage="quarantined",
            )

        if not dataset.verified:
            return reject(
                ("DATASET_UNVERIFIED",),
                f"dataset {dataset.dataset_id} has not passed verification",
            )

        dataset = self._bind_shadow_window(candidate, dataset)

        if not self._autonomy.is_full_autonomy():
            state = self._autonomy.state()
            return reject(
                ("AUTONOMY_REVOKED",),
                f"autonomy is revoked: {state['revoked_reason'] or 'no reason recorded'}",
            )

        if (
            dataset.shadow.candidate_id is not None
            and dataset.shadow.candidate_id != candidate.genome_id
        ):
            return reject(
                ("SHADOW_EVIDENCE_MISMATCH",),
                "shadow evidence belongs to another candidate",
            )
        if dataset.dataset_id.startswith("app:") and dataset.shadow.candidate_id is None:
            return reject(
                ("SHADOW_EVIDENCE_UNBOUND",),
                "paper shadow evidence is not candidate-bound",
            )

        allowed, churn_reason = self._pipeline.can_promote_to_active()
        if not allowed:
            return reject((churn_reason or "PROMOTION_BLOCKED",), "promotion churn guard is active")

        gate_reports: dict[str, Any] = {}
        try:
            gates = self._run_gates(candidate, dataset, gate_reports)
        except Exception as exc:
            # An autonomous loop must survive a bad dataset or a harness error without
            # crashing its caller; the candidate simply does not advance.
            return reject(
                ("EVALUATION_ERROR",),
                f"gate evaluation failed: {exc}",
                gate_reports=gate_reports,
            )

        failed = next((gate for gate in gates if not gate.passed), None)
        if failed is not None:
            return reject(
                failed.failure_reasons or (f"{failed.gate_name.upper()}_GATE_FAILED",),
                f"{failed.gate_name} gate rejected the candidate",
                stage=self._genomes.get_genome_status(candidate.genome_id) or "candidate",
                gate_reports=gate_reports,
            )

        if not self._autonomy.is_full_autonomy():
            state = self._autonomy.state()
            return reject(("AUTONOMY_REVOKED",), f"autonomy is revoked: {state['revoked_reason']}")

        if not commit:
            return PromotionDecision(
                promoted=True,
                stage="validated",
                candidate_id=candidate.genome_id,
                candidate_hash=candidate_hash,
                baseline_id=baseline.genome_id,
                baseline_hash=baseline_hash,
                dataset_id=dataset.dataset_id,
                detail="gates passed; activation held",
                rejection_reasons=(),
                gate_reports=gate_reports,
            )

        promotion_id = f"prom-{uuid4().hex[:8]}"
        try:
            self._pipeline.promote_to_active(
                candidate.genome_id,
                promoted_by=PROMOTED_BY,
                mode="canary",
                promotion_id=promotion_id,
                autonomy_repo=self._autonomy,
                baseline_genome_id=baseline.genome_id,
                baseline_hash=baseline_hash,
                gate_report={
                    "baseline_genome_id": baseline.genome_id,
                    "baseline_hash": baseline_hash,
                    "candidate_hash": candidate_hash,
                    "dataset_id": dataset.dataset_id,
                    "gates": gate_reports,
                },
            )
        except ValueError as exc:
            detail = str(exc)
            if detail.startswith("AUTONOMY_REVOKED:"):
                return reject(("AUTONOMY_REVOKED",), detail, gate_reports=gate_reports)
            raise
        return PromotionDecision(
            promoted=True,
            stage="canary",
            candidate_id=candidate.genome_id,
            candidate_hash=candidate_hash,
            baseline_id=baseline.genome_id,
            baseline_hash=baseline_hash,
            dataset_id=dataset.dataset_id,
            detail="all gates passed; promoted to active under canary observation",
            promoted_by=PROMOTED_BY,
            promotion_id=promotion_id,
            gate_reports=gate_reports,
        )

    def _run_gates(
        self,
        candidate: StrategyGenome,
        dataset: EvidenceDataset,
        gate_reports: dict[str, Any],
    ) -> list[GateResult]:
        """Gates in order, stopping at the first failure. The sealed holdout partition is
        only opened once validation has passed."""
        gates: list[GateResult] = []
        candles = dataset.candles_15m

        self._consume_backtest()
        dev_run = self._engine.run(candidate, candles)
        dev = self._pipeline.evaluate_dev_gate(
            candidate.genome_id,
            dev_run.report,
            dev_run.run_hash,
        )
        gates.append(dev)
        gate_reports["development"] = dev.metrics
        if not dev.passed:
            return gates

        self._consume_backtest()
        walk_forward = self._harness.evaluate(
            genome=candidate,
            candles_15m=candles,
            unlock_holdout=False,
        )
        validation = self._pipeline.evaluate_val_gate(
            candidate.genome_id,
            walk_forward,
            f"wf-{dataset.dataset_id}-{candidate.genome_id}",
        )
        gates.append(validation)
        gate_reports["validation"] = validation.metrics
        if not validation.passed:
            return gates

        # ponytail: a second walk-forward pass re-runs the windows to reach the sealed
        # partition. Promotion runs at most once a day, so the cost is irrelevant; split
        # the sealed evaluation out of the harness if that ever stops being true.
        self._consume_backtest()
        sealed = self._harness.evaluate(
            genome=candidate,
            candles_15m=candles,
            unlock_holdout=True,
            promotion_token=f"prom_gate_{genome_hash(candidate)[:16]}",
        )
        holdout_report = _holdout_report(sealed)
        holdout = self._pipeline.evaluate_holdout_gate(
            candidate,
            holdout_report,
            f"holdout-{dataset.dataset_id}-{candidate.genome_id}",
        )
        gates.append(holdout)
        gate_reports["holdout"] = holdout.metrics
        if not holdout.passed:
            return gates

        shadow = self._pipeline.evaluate_shadow_gate(
            candidate.genome_id,
            shadow_days=dataset.shadow.days,
            shadow_net_pnl=dataset.shadow.net_pnl,
            shadow_trades=dataset.shadow.trades,
            slippage_acceptable=dataset.shadow.slippage_acceptable,
        )
        gates.append(shadow)
        gate_reports["shadow"] = shadow.metrics
        return gates

    def _bind_shadow_window(
        self,
        candidate: StrategyGenome,
        dataset: EvidenceDataset,
    ) -> EvidenceDataset:
        """Reserve the last 14 days of verified 15m history as candidate-bound shadow.

        Live paper trades of the baseline are not evidence for a candidate. When the
        dataset is long enough, the tail is measured for this genome and excluded
        from the development / validation / holdout candles.
        """

        if dataset.shadow.candidate_id == candidate.genome_id:
            return dataset
        candles = dataset.candles_15m
        if len(candles) < SHADOW_WINDOW_BARS_15M + 400:
            return dataset
        if not hasattr(candles[0], "open_time"):
            return dataset
        body = candles[:-SHADOW_WINDOW_BARS_15M]
        tail = candles[-SHADOW_WINDOW_BARS_15M:]
        try:
            self._consume_backtest()
            run = self._engine.run(candidate, tail)
            report = run.report
        except Exception:
            return dataset
        first = tail[0].open_time
        last = tail[-1].open_time
        days = max((last - first).days + 1, 0)
        shadow = ShadowEvidence(
            days=days,
            net_pnl=report.net_pnl,
            trades=int(report.trade_count),
            slippage_acceptable=True,
            candidate_id=candidate.genome_id,
        )
        return EvidenceDataset(
            dataset_id=dataset.dataset_id,
            verified=dataset.verified,
            candles_15m=body,
            shadow=shadow,
        )

    # -- rollback ------------------------------------------------------------------

    def on_canary_event(self, event: CanaryEvent) -> RollbackDecision | None:
        """Revert the canary when it breaches its bounds. Returns None when it is healthy,
        already closed, or was never promoted by this controller."""
        canary = self._promotions.get_canary(event.genome_id)
        if canary is None or canary["stage"] != "canary":
            return None

        reasons: list[str] = []
        if event.drawdown > self._canary.max_drawdown:
            reasons.append(
                f"CANARY_DRAWDOWN_EXCEEDED({event.drawdown} > {self._canary.max_drawdown})"
            )
        if event.error_count >= self._canary.max_errors:
            reasons.append(
                f"CANARY_ERROR_BUDGET_EXCEEDED({event.error_count} >= {self._canary.max_errors})"
            )
        if not reasons:
            return None

        reason = "; ".join(reasons)
        # Close first: the update is conditional on the canary still being open, so two
        # concurrent breach signals cannot both roll back the same candidate.
        if not self._promotions.close_canary(
            event.genome_id,
            stage="rolled_back",
            rollback_reason=reason,
            circuit_breaker_tripped=True,
        ):
            return None

        baseline_id = str(canary["baseline_genome_id"])
        self._genomes.update_status(event.genome_id, "quarantined")
        restored: str | None = None
        if self._genomes.get_genome(baseline_id) is not None:
            self._genomes.update_status(baseline_id, "active")
            restored = baseline_id

        self._promotions.record_promotion(
            promotion_id=f"rollback-{event.genome_id[:24]}-{canary['promotion_id'][-8:]}",
            genome_id=baseline_id if restored else event.genome_id,
            promoted_by=PROMOTED_BY,
            mode="rollback",
            gate_report={
                "rolled_back_genome_id": event.genome_id,
                "restored_genome_id": restored,
                "reason": reason,
                "drawdown": str(event.drawdown),
                "error_count": event.error_count,
                "trades": event.trades,
            },
        )
        return RollbackDecision(
            genome_id=event.genome_id,
            restored_genome_id=restored,
            reason=reason,
            circuit_breaker_tripped=True,
        )

    def confirm_canary(self, genome_id: str) -> bool:
        """Mark an observed canary as settled. Returns False if it was already closed."""
        return self._promotions.close_canary(genome_id, stage="confirmed")


def risk_bound_violations(
    candidate: StrategyGenome,
    baseline: StrategyGenome,
) -> tuple[str, ...]:
    """Names of every protective bound the candidate loosens relative to the baseline.

    Tightening is always allowed; only widening a stop, shrinking a target, or relaxing a
    data-quality guard is a violation.
    """
    checks: tuple[tuple[bool, str], ...] = (
        (candidate.exit.stop_atr_multiple > baseline.exit.stop_atr_multiple, "STOP_WIDENED"),
        (candidate.exit.r_multiple_min < baseline.exit.r_multiple_min, "TARGET_SHRUNK"),
        (candidate.guard.max_spread_rate > baseline.guard.max_spread_rate, "SPREAD_GUARD_LOOSENED"),
        (candidate.guard.max_atr_rate > baseline.guard.max_atr_rate, "ATR_CEILING_RAISED"),
        (candidate.guard.min_atr_rate < baseline.guard.min_atr_rate, "ATR_FLOOR_LOWERED"),
        (
            not candidate.exit.regime_invalidation and baseline.exit.regime_invalidation,
            "REGIME_EXIT_DISABLED",
        ),
    )
    return tuple(name for violated, name in checks if violated)


def _holdout_report(sealed: WalkForwardReport) -> PerformanceReport:
    if sealed.holdout_result is None:
        raise ValueError("sealed holdout partition returned no result")
    return sealed.holdout_result.report
