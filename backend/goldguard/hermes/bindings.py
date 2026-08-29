from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from goldguard.backtest.engine import BacktestEngine
from goldguard.backtest.reports import report_to_dict
from goldguard.domain.enums import ExecutionMode, ProductKind
from goldguard.execution.models import MarketScope
from goldguard.storage.evidence_repository import EvidenceRepository
from goldguard.storage.repositories import (
    EvaluationRepository,
    GenomeRepository,
    LedgerRepository,
    MarketCandleRepository,
    ReflectionRepository,
)
from goldguard.strategy.genome import StrategyGenome
from goldguard.strategy.indicators import atr_wilder, ema_series, rsi_wilder

MAX_CANDLES = 500


def build_tool_bindings(
    *,
    candle_repo: MarketCandleRepository | None = None,
    ledger_repo: LedgerRepository | None = None,
    genome_repo: GenomeRepository | None = None,
    reflection_repo: ReflectionRepository | None = None,
    evidence_repo: EvidenceRepository | None = None,
    evaluation_repo: EvaluationRepository | None = None,
    backtest_engine: BacktestEngine | None = None,
    symbol: str = "PAXGUSDT",
) -> dict[str, Any]:
    """Wire allowlisted Hermes tools to real stores. Empty observations stay empty."""

    async def get_candles(payload: dict[str, Any], principal: Any = None) -> dict[str, Any]:
        _ = principal
        requested = str(payload.get("symbol") or symbol)
        timeframe = str(payload.get("timeframe") or "15m")
        try:
            limit = min(int(payload.get("limit", 200)), MAX_CANDLES)
        except (TypeError, ValueError):
            limit = 200
        if candle_repo is None:
            return {
                "available": False,
                "reason": "MARKET_STORE_NOT_BOUND",
                "candles": [],
                "symbol": requested,
            }
        candles = candle_repo.load_candles(requested, timeframe, limit)
        return {
            "available": True,
            "symbol": requested,
            "timeframe": timeframe,
            "candles": [
                {
                    "open_time": item.open_time.isoformat(),
                    "close_time": item.close_time.isoformat(),
                    "open": str(item.open),
                    "high": str(item.high),
                    "low": str(item.low),
                    "close": str(item.close),
                    "volume": str(item.volume),
                }
                for item in candles
            ],
        }

    async def get_features(payload: dict[str, Any], principal: Any = None) -> dict[str, Any]:
        _ = principal
        requested = str(payload.get("symbol") or symbol)
        if candle_repo is None:
            return {"available": False, "reason": "FEATURE_STORE_NOT_BOUND", "features": {}}
        candles = candle_repo.load_candles(requested, "15m", 80)
        if len(candles) < 30:
            return {"available": False, "reason": "INSUFFICIENT_CANDLES", "features": {}}
        closes = [float(item.close) for item in candles]
        highs = [float(item.high) for item in candles]
        lows = [float(item.low) for item in candles]
        ema20 = ema_series(closes, 20)
        rsi = rsi_wilder(closes, 14)
        atr = atr_wilder(highs, lows, closes, 14)
        last_ema = ema20[-1] if ema20 else None
        last_rsi = rsi[-1] if rsi else None
        last_atr = atr[-1] if atr else None
        return {
            "available": True,
            "symbol": requested,
            "features": {
                "close": str(candles[-1].close),
                "ema20": None if last_ema is None else str(Decimal(str(last_ema))),
                "rsi14": None if last_rsi is None else str(Decimal(str(last_rsi))),
                "atr14": None if last_atr is None else str(Decimal(str(last_atr))),
                "bar_count": len(candles),
            },
        }

    async def get_evidence(payload: dict[str, Any], principal: Any = None) -> dict[str, Any]:
        _ = principal
        requested = str(payload.get("symbol") or symbol)
        if evidence_repo is None:
            return {"available": False, "reason": "EVIDENCE_STORE_NOT_BOUND", "evidence": []}
        scope = MarketScope(
            mode=ExecutionMode.PAPER,
            product=ProductKind.SPOT,
            symbol=requested,
        )
        bundle = evidence_repo.bundle_for(scope, datetime.now(UTC))
        return {
            "available": True,
            "symbol": requested,
            "disposition": bundle.disposition.value,
            "evidence": [
                {
                    "evidence_id": item.evidence_id,
                    "title": item.title,
                    "source_kind": item.source_kind.value,
                    "published_at": item.published_at.isoformat() if item.published_at else None,
                    "event_class": item.event_class,
                }
                for item in bundle.items
            ],
        }

    async def get_trade_outcomes(payload: dict[str, Any], principal: Any = None) -> dict[str, Any]:
        _ = payload, principal
        if ledger_repo is None:
            return {"available": False, "reason": "OUTCOME_STORE_NOT_BOUND", "trades": []}
        session_id = ledger_repo.current_paper_session_id()
        if session_id is None:
            return {"available": True, "trades": []}
        rows = ledger_repo.list_trades(session_id)
        trades: list[dict[str, Any]] = []
        for row in rows:
            trades.append(
                {
                    "id": str(row.get("id") or row.get("trade_id") or ""),
                    "side": str(row.get("side") or ""),
                    "opened_at": str(row.get("opened_at") or ""),
                    "closed_at": str(row.get("closed_at") or ""),
                    "realized_pnl": str(
                        row.get("realized_pnl_text") or row.get("realized_pnl") or ""
                    ),
                }
            )
        return {"available": True, "trades": trades}

    async def get_lessons(payload: dict[str, Any], principal: Any = None) -> dict[str, Any]:
        _ = principal
        if reflection_repo is None:
            return {"available": False, "reason": "LESSON_STORE_NOT_BOUND", "lessons": []}
        namespace = payload.get("namespace")
        ns = str(namespace) if isinstance(namespace, str) and namespace else None
        lessons = reflection_repo.list_reflections(namespace=ns, limit=50)
        return {"available": True, "lessons": lessons}

    async def run_backtest(payload: dict[str, Any], principal: Any = None) -> dict[str, Any]:
        _ = principal
        if backtest_engine is None or candle_repo is None or genome_repo is None:
            return {
                "available": False,
                "reason": "BACKTEST_RUNNER_NOT_BOUND",
                "trades": [],
            }
        genome_id = str(payload.get("genome_id") or "")
        genome = genome_repo.get_genome(genome_id) if genome_id else None
        if genome is None:
            return {
                "available": False,
                "reason": "GENOME_NOT_FOUND",
                "trades": [],
            }
        candles_15m = candle_repo.load_candles(symbol, "15m", MAX_CANDLES)
        candles_1h = candle_repo.load_candles(symbol, "1h", MAX_CANDLES)
        if len(candles_15m) < 30:
            return {
                "available": False,
                "reason": "INSUFFICIENT_CANDLES",
                "trades": [],
            }
        result = backtest_engine.run(genome, candles_15m, candles_1h or None)
        return {
            "available": True,
            "genome_id": genome.genome_id,
            "run_hash": result.run_hash,
            "trade_count": len(result.trades),
            "metrics": report_to_dict(result.report),
            "trades": [
                {
                    "exit_reason": trade.exit_reason.value
                    if hasattr(trade.exit_reason, "value")
                    else str(trade.exit_reason),
                    "realized_pnl": str(trade.realized_pnl),
                }
                for trade in result.trades
            ],
        }

    async def get_evaluation(payload: dict[str, Any], principal: Any = None) -> dict[str, Any]:
        _ = principal
        partition = str(payload.get("partition") or "development")
        genome_id = str(payload.get("genome_id") or "")
        if evaluation_repo is None:
            return {
                "available": False,
                "reason": "EVALUATION_NOT_BOUND",
                "partition": partition,
                "passed": False,
            }
        rows = evaluation_repo.get_evaluations_for_genome(genome_id) if genome_id else []
        matching = [row for row in rows if str(row.get("partition")) == partition]
        if not matching:
            return {
                "available": False,
                "reason": "EVALUATION_NOT_FOUND",
                "partition": partition,
                "passed": False,
            }
        latest = matching[0]
        return {
            "available": True,
            "partition": partition,
            "passed": False,
            "evaluation_id": str(latest.get("evaluation_id") or ""),
            "run_hash": str(latest.get("run_hash") or ""),
        }

    async def submit_genome(payload: dict[str, Any], principal: Any = None) -> dict[str, Any]:
        _ = principal
        if genome_repo is None:
            return {
                "available": False,
                "reason": "GENOME_SERVICE_NOT_BOUND",
                "status": "rejected",
            }
        raw = payload.get("genome")
        if not isinstance(raw, dict):
            return {
                "available": False,
                "reason": "INVALID_GENOME",
                "status": "rejected",
            }
        try:
            genome = StrategyGenome.model_validate(raw)
        except Exception as exc:
            return {
                "available": False,
                "reason": "INVALID_GENOME",
                "status": "rejected",
                "detail": str(exc)[:300],
            }
        genome_repo.save_genome(genome, origin="hermes", status="candidate")
        return {
            "available": True,
            "status": "accepted_candidate",
            "genome_id": genome.genome_id,
        }

    return {
        "get_candles": get_candles,
        "get_features": get_features,
        "get_evidence": get_evidence,
        "get_trade_outcomes": get_trade_outcomes,
        "get_lessons": get_lessons,
        "run_backtest": run_backtest,
        "get_evaluation": get_evaluation,
        "submit_genome": submit_genome,
    }
