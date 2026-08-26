from dataclasses import dataclass
from decimal import Decimal
from typing import TYPE_CHECKING, Any, Literal, Protocol
from uuid import uuid4

from goldguard.backtest.metrics import PerformanceReport
from goldguard.backtest.reports import report_to_dict
from goldguard.backtest.walk_forward import WalkForwardReport
from goldguard.strategy.genome import StrategyGenome

if TYPE_CHECKING:
    from goldguard.storage.repositories import (
        EvaluationRepository,
        GenomeRepository,
        PromotionRepository,
    )


class GenomeRepoProtocol(Protocol):
    def update_status(self, genome_id: str, new_status: str) -> None: ...
    def get_active_genome(self) -> StrategyGenome | None: ...


class EvalRepoProtocol(Protocol):
    def record_evaluation(
        self,
        *,
        genome_id: str,
        partition: str,
        window: str,
        metrics: dict[str, Any],
        run_hash: str,
        evaluation_id: str | None = None,
    ) -> None: ...


class PromotionRepoProtocol(Protocol):
    def record_promotion(
        self,
        *,
        promotion_id: str,
        genome_id: str,
        promoted_by: str,
        mode: str,
        gate_report: dict[str, Any],
    ) -> None: ...
    def get_promotions_in_last_days(self, days: int = 7) -> int: ...


PromotionStage = Literal[
    "candidate",
    "dev_passed",
    "val_passed",
    "holdout_passed",
    "shadow",
    "active",
    "quarantined",
]


@dataclass(frozen=True)
class DevGateConfig:
    min_win_rate: Decimal = Decimal("0.40")
    min_profit_factor: Decimal = Decimal("1.20")
    min_trade_count: int = 30


@dataclass(frozen=True)
class ValGateConfig:
    min_wfe: Decimal = Decimal("0.50")
    min_dsr: Decimal = Decimal("0.95")
    max_drawdown: Decimal = Decimal("0.15")


@dataclass(frozen=True)
class HoldoutGateConfig:
    min_net_return: Decimal = Decimal("0.0")
    max_drawdown: Decimal = Decimal("0.15")


@dataclass(frozen=True)
class ShadowGateConfig:
    min_days: int = 14
    min_net_pnl: Decimal = Decimal("0.0")
    min_trade_count: int = 5
    max_slippage_multiplier: Decimal = Decimal("1.5")


@dataclass(frozen=True)
class GateResult:
    gate_name: str
    passed: bool
    metrics: dict[str, Any]
    failure_reasons: tuple[str, ...]


class PromotionPipeline:
    """Rigorous 4-gate strategy promotion pipeline with permanent quarantine on holdout failure."""

    def __init__(
        self,
        *,
        genome_repo: "GenomeRepository | GenomeRepoProtocol",
        eval_repo: "EvaluationRepository | EvalRepoProtocol",
        promotion_repo: "PromotionRepository | PromotionRepoProtocol",
        dev_config: DevGateConfig | None = None,
        val_config: ValGateConfig | None = None,
        holdout_config: HoldoutGateConfig | None = None,
        shadow_config: ShadowGateConfig | None = None,
    ) -> None:
        self.genome_repo = genome_repo
        self.eval_repo = eval_repo
        self.promotion_repo = promotion_repo
        self.dev_config = dev_config or DevGateConfig()
        self.val_config = val_config or ValGateConfig()
        self.holdout_config = holdout_config or HoldoutGateConfig()
        self.shadow_config = shadow_config or ShadowGateConfig()

    def evaluate_dev_gate(
        self,
        genome_id: str,
        report: PerformanceReport,
        run_hash: str,
    ) -> GateResult:
        reasons: list[str] = []
        if report.win_rate < self.dev_config.min_win_rate:
            reasons.append("LOW_WIN_RATE")
        if report.profit_factor is None or report.profit_factor < self.dev_config.min_profit_factor:
            reasons.append("LOW_PROFIT_FACTOR")
        if report.trade_count < self.dev_config.min_trade_count:
            reasons.append("INSUFFICIENT_TRADES")

        passed = len(reasons) == 0
        metrics = report_to_dict(report)

        self.eval_repo.record_evaluation(
            genome_id=genome_id,
            partition="development",
            window="in_sample",
            metrics=metrics,
            run_hash=run_hash,
        )

        if passed:
            self.genome_repo.update_status(genome_id, "dev_passed")

        return GateResult(
            gate_name="development",
            passed=passed,
            metrics=metrics,
            failure_reasons=tuple(reasons),
        )

    def evaluate_val_gate(
        self,
        genome_id: str,
        wf_report: WalkForwardReport,
        run_hash: str,
    ) -> GateResult:
        reasons: list[str] = []
        if wf_report.wfe < self.val_config.min_wfe:
            reasons.append("LOW_WALK_FORWARD_EFFICIENCY")
        if wf_report.deflated_sharpe_ratio < self.val_config.min_dsr:
            reasons.append("DEFLATED_SHARPE_FAIL")
        if wf_report.max_out_of_sample_drawdown > self.val_config.max_drawdown:
            reasons.append("MAX_DRAWDOWN_EXCEEDED")

        passed = len(reasons) == 0
        metrics = {
            "wfe": str(wf_report.wfe),
            "dsr": str(wf_report.deflated_sharpe_ratio),
            "pbo": str(wf_report.pbo),
            "max_oos_drawdown": str(wf_report.max_out_of_sample_drawdown),
        }

        self.eval_repo.record_evaluation(
            genome_id=genome_id,
            partition="validation",
            window="walk_forward",
            metrics=metrics,
            run_hash=run_hash,
        )

        if passed:
            self.genome_repo.update_status(genome_id, "val_passed")

        return GateResult(
            gate_name="validation",
            passed=passed,
            metrics=metrics,
            failure_reasons=tuple(reasons),
        )

    def evaluate_holdout_gate(
        self,
        genome: StrategyGenome,
        holdout_report: PerformanceReport,
        run_hash: str,
    ) -> GateResult:
        reasons: list[str] = []
        if holdout_report.net_return <= self.holdout_config.min_net_return:
            reasons.append("NEGATIVE_HOLDOUT_RETURN")
        if holdout_report.maximum_drawdown > self.holdout_config.max_drawdown:
            reasons.append("HOLDOUT_MAX_DRAWDOWN_EXCEEDED")

        passed = len(reasons) == 0
        metrics = report_to_dict(holdout_report)

        self.eval_repo.record_evaluation(
            genome_id=genome.genome_id,
            partition="holdout",
            window="sealed_final",
            metrics=metrics,
            run_hash=run_hash,
        )

        if passed:
            self.genome_repo.update_status(genome.genome_id, "holdout_passed")
        else:
            self.genome_repo.update_status(genome.genome_id, "quarantined")

        return GateResult(
            gate_name="holdout",
            passed=passed,
            metrics=metrics,
            failure_reasons=tuple(reasons),
        )

    def evaluate_shadow_gate(
        self,
        genome_id: str,
        *,
        shadow_days: int,
        shadow_net_pnl: Decimal,
        shadow_trades: int,
        slippage_acceptable: bool = True,
    ) -> GateResult:
        reasons: list[str] = []
        if shadow_days < self.shadow_config.min_days:
            reasons.append("INSUFFICIENT_SHADOW_DURATION")
        if shadow_net_pnl < self.shadow_config.min_net_pnl:
            reasons.append("NEGATIVE_SHADOW_PNL")
        if shadow_trades < self.shadow_config.min_trade_count:
            reasons.append("INSUFFICIENT_SHADOW_TRADES")
        if not slippage_acceptable:
            reasons.append("EXCESSIVE_SHADOW_SLIPPAGE")

        passed = len(reasons) == 0
        metrics = {
            "shadow_days": shadow_days,
            "shadow_net_pnl": str(shadow_net_pnl),
            "shadow_trades": shadow_trades,
            "slippage_acceptable": slippage_acceptable,
        }

        if passed:
            self.genome_repo.update_status(genome_id, "shadow")

        return GateResult(
            gate_name="shadow",
            passed=passed,
            metrics=metrics,
            failure_reasons=tuple(reasons),
        )

    def can_promote_to_active(self, full_autonomy: bool = False) -> tuple[bool, str | None]:
        promotions_today = self.promotion_repo.get_promotions_in_last_days(days=1)
        if promotions_today >= 1:
            return False, "PROMOTION_CHURN_HALT"
        return True, None

    def promote_to_active(
        self,
        genome_id: str,
        *,
        promoted_by: str = "hermes_autonomy",
        mode: str = "active",
        gate_report: dict[str, Any] | None = None,
    ) -> str:
        can_promote, reason = self.can_promote_to_active()
        if not can_promote:
            raise ValueError(f"Cannot promote strategy: {reason}")

        current_active = self.genome_repo.get_active_genome()
        if current_active and current_active.genome_id != genome_id:
            self.genome_repo.update_status(current_active.genome_id, "archived")

        self.genome_repo.update_status(genome_id, "active")
        promotion_id = f"prom-{uuid4().hex[:8]}"
        self.promotion_repo.record_promotion(
            promotion_id=promotion_id,
            genome_id=genome_id,
            promoted_by=promoted_by,
            mode=mode,
            gate_report=gate_report or {"status": "promoted_to_active"},
        )
        return promotion_id
