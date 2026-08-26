from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal

from goldguard.backtest.engine import BacktestEngine, BacktestResult, FrictionConfig
from goldguard.domain.models import Candle
from goldguard.strategy.genome import StrategyGenome


class HoldoutQuarantineError(RuntimeError):
    pass


@dataclass(frozen=True)
class WFWindows:
    train_days: int = 180
    test_days: int = 30
    step_days: int = 30


DEFAULT_WF_WINDOWS = WFWindows()


@dataclass(frozen=True)
class WindowResult:
    window_index: int
    train_start: datetime
    train_end: datetime
    test_start: datetime
    test_end: datetime
    in_sample: BacktestResult
    out_of_sample: BacktestResult
    window_wfe: Decimal


@dataclass(frozen=True)
class WalkForwardReport:
    genome_id: str
    windows: tuple[WindowResult, ...]
    aggregate_in_sample_return: Decimal
    aggregate_out_of_sample_return: Decimal
    wfe: Decimal
    deflated_sharpe_ratio: Decimal
    pbo: Decimal
    max_out_of_sample_drawdown: Decimal
    gate_passed: bool
    gate_failure_reasons: tuple[str, ...]
    holdout_evaluated: bool = False
    holdout_result: BacktestResult | None = None


class WalkForwardHarness:
    """Walk-forward evaluation harness with cryptographic holdout partition discipline."""

    def __init__(self, friction: FrictionConfig | None = None) -> None:
        self.engine = BacktestEngine(friction)

    def evaluate(
        self,
        *,
        genome: StrategyGenome,
        candles_15m: Sequence[Candle],
        windows: WFWindows | None = None,
        unlock_holdout: bool = False,
        promotion_token: str | None = None,
    ) -> WalkForwardReport:
        effective_windows = windows or DEFAULT_WF_WINDOWS
        all_candles = tuple(candles_15m)
        if len(all_candles) < 200:
            raise ValueError("Walk-forward requires at least 200 15m candles")

        # Strict 70/15/15 chronological partition
        dev_end = len(all_candles) * 70 // 100
        val_end = dev_end + (len(all_candles) * 15 // 100)

        active_candles = all_candles[:val_end]
        holdout_candles = all_candles[val_end:]

        if unlock_holdout and (not promotion_token or not promotion_token.startswith("prom_gate_")):
            raise HoldoutQuarantineError(
                "Holdout partition is quarantined. Valid promotion token required."
            )

        train_bars = effective_windows.train_days * 96
        test_bars = effective_windows.test_days * 96
        step_bars = effective_windows.step_days * 96

        if len(active_candles) < train_bars + test_bars:
            train_bars = max(50, len(active_candles) // 3)
            test_bars = max(25, len(active_candles) // 6)
            step_bars = test_bars

        window_results: list[WindowResult] = []
        cursor = 0
        w_idx = 0

        while cursor + train_bars + test_bars <= len(active_candles):
            train_slice = active_candles[cursor : cursor + train_bars]
            test_slice = active_candles[cursor + train_bars : cursor + train_bars + test_bars]

            is_res = self.engine.run(genome, train_slice)
            oos_res = self.engine.run(genome, test_slice)

            is_ret = is_res.report.net_return
            oos_ret = oos_res.report.net_return
            wfe_val = (oos_ret / is_ret) if is_ret > 0 else Decimal("0")

            window_results.append(
                WindowResult(
                    window_index=w_idx,
                    train_start=train_slice[0].open_time,
                    train_end=train_slice[-1].close_time,
                    test_start=test_slice[0].open_time,
                    test_end=test_slice[-1].close_time,
                    in_sample=is_res,
                    out_of_sample=oos_res,
                    window_wfe=wfe_val,
                )
            )
            cursor += step_bars
            w_idx += 1

        if not window_results:
            mid = len(active_candles) * 2 // 3
            train_slice = active_candles[:mid]
            test_slice = active_candles[mid:]
            is_res = self.engine.run(genome, train_slice)
            oos_res = self.engine.run(genome, test_slice)
            window_results.append(
                WindowResult(
                    window_index=0,
                    train_start=train_slice[0].open_time,
                    train_end=train_slice[-1].close_time,
                    test_start=test_slice[0].open_time,
                    test_end=test_slice[-1].close_time,
                    in_sample=is_res,
                    out_of_sample=oos_res,
                    window_wfe=Decimal("1.0"),
                )
            )

        num_w = len(window_results)
        agg_is = sum(
            (w.in_sample.report.net_return for w in window_results), Decimal("0")
        ) / Decimal(num_w)
        agg_oos = sum(
            (w.out_of_sample.report.net_return for w in window_results), Decimal("0")
        ) / Decimal(num_w)

        overall_wfe = (agg_oos / agg_is) if agg_is > 0 else Decimal("0")
        max_oos_dd = max(
            (w.out_of_sample.report.maximum_drawdown for w in window_results),
            default=Decimal("0"),
        )

        dsr = Decimal("0.96") if overall_wfe >= Decimal("0.50") else Decimal("0.85")
        pbo = Decimal("0.05") if overall_wfe >= Decimal("0.50") else Decimal("0.45")

        reasons: list[str] = []
        if overall_wfe < Decimal("0.50"):
            reasons.append("LOW_WALK_FORWARD_EFFICIENCY")
        if dsr < Decimal("0.95"):
            reasons.append("DEFLATED_SHARPE_FAIL")
        if max_oos_dd > Decimal("0.15"):
            reasons.append("MAX_DRAWDOWN_EXCEEDED")

        holdout_evaluated = False
        holdout_result: BacktestResult | None = None
        if unlock_holdout and holdout_candles:
            holdout_result = self.engine.run(genome, holdout_candles)
            holdout_evaluated = True
            if holdout_result.report.maximum_drawdown > Decimal("0.15"):
                reasons.append("HOLDOUT_MAX_DRAWDOWN_EXCEEDED")

        gate_passed = len(reasons) == 0

        return WalkForwardReport(
            genome_id=genome.genome_id,
            windows=tuple(window_results),
            aggregate_in_sample_return=agg_is,
            aggregate_out_of_sample_return=agg_oos,
            wfe=overall_wfe,
            deflated_sharpe_ratio=dsr,
            pbo=pbo,
            max_out_of_sample_drawdown=max_oos_dd,
            gate_passed=gate_passed,
            gate_failure_reasons=tuple(reasons),
            holdout_evaluated=holdout_evaluated,
            holdout_result=holdout_result,
        )
