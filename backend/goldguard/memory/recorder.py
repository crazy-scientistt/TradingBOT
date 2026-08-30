"""Closed-paper-trade → one durable reflection. Same transaction or outbox."""

from __future__ import annotations

import sqlite3
from decimal import Decimal

from goldguard.broker.base import ClosedPaperTrade
from goldguard.memory.engine import MemoryBank
from goldguard.memory.reflections import ReflectionEngine, TradeOutcome
from goldguard.storage.repositories import ReflectionRepository


class LearningRecorder:
    def __init__(self, reflection_repo: ReflectionRepository) -> None:
        self._repo = reflection_repo
        self._engine = ReflectionEngine()
        self._bank = MemoryBank(reflection_repo)

    def already_recorded(self, trade_id: str) -> bool:
        return self._repo.get_by_trade_id(trade_id) is not None

    def has_pending_outbox(self) -> bool:
        return self._repo.has_pending_outbox()

    def record_closed_trade(
        self,
        trade: ClosedPaperTrade,
        *,
        trade_id: str,
        symbol: str,
        genome_id: str | None = None,
        hypothesis: str = "paper closed cycle",
        mae: Decimal | None = None,
        mfe: Decimal | None = None,
        connection: sqlite3.Connection | None = None,
    ) -> str | None:
        if self.already_recorded(trade_id):
            return None
        fees = trade.entry_fill.fee + trade.exit_fill.fee
        outcome = TradeOutcome(
            trade_id=trade_id,
            namespace="forward",
            hypothesis=hypothesis,
            realized_pnl=trade.realized_pnl,
            maximum_adverse_excursion=mae if mae is not None else Decimal("0"),
            maximum_favorable_excursion=mfe if mfe is not None else Decimal("0"),
            fees=fees,
            exit_reason=trade.exit_reason.value,
            regime_tags=(symbol,),
        )
        reflection = self._engine.create(outcome)
        payload = {
            "hypothesis": reflection.hypothesis,
            "genome_id": genome_id or "",
            "symbol": symbol,
            "realized_pnl": str(trade.realized_pnl),
            "mae": str(outcome.maximum_adverse_excursion),
            "mfe": str(outcome.maximum_favorable_excursion),
            "fees": str(fees),
            "exit_reason": trade.exit_reason.value,
            "namespace": reflection.namespace,
        }
        try:
            if connection is not None:
                self._repo.record_reflection(
                    reflection_id=reflection.identifier,
                    trade_id=trade_id,
                    namespace=reflection.namespace,
                    lesson_code=reflection.lesson_code,
                    lesson=reflection.lesson,
                    regime_tags=list(reflection.regime_tags),
                    net_pnl=reflection.net_pnl,
                    fee_drag=reflection.fee_drag,
                    mae=reflection.maximum_adverse_excursion,
                    mfe=reflection.maximum_favorable_excursion,
                    exit_reason=reflection.exit_reason,
                    payload=payload,
                    connection=connection,
                )
                self._repo.mark_outbox(connection, trade_id, "done")
                return reflection.identifier
            with self._repo.database.transaction() as owned:
                self._repo.record_reflection(
                    reflection_id=reflection.identifier,
                    trade_id=trade_id,
                    namespace=reflection.namespace,
                    lesson_code=reflection.lesson_code,
                    lesson=reflection.lesson,
                    regime_tags=list(reflection.regime_tags),
                    net_pnl=reflection.net_pnl,
                    fee_drag=reflection.fee_drag,
                    mae=reflection.maximum_adverse_excursion,
                    mfe=reflection.maximum_favorable_excursion,
                    exit_reason=reflection.exit_reason,
                    payload=payload,
                    connection=owned,
                )
                self._repo.mark_outbox(owned, trade_id, "done")
            return reflection.identifier
        except Exception as exc:
            self._repo.enqueue_outbox(
                trade_id=trade_id,
                payload=payload,
                error=str(exc),
                connection=connection,
            )
            return None

    def drain_outbox(self) -> int:
        drained = 0
        for item in self._repo.list_pending_outbox():
            trade_id = item["trade_id"]
            if self.already_recorded(trade_id):
                with self._repo.database.transaction() as connection:
                    self._repo.mark_outbox(connection, trade_id, "done")
                drained += 1
                continue
            payload = item.get("payload") or {}
            try:
                outcome = TradeOutcome(
                    trade_id=trade_id,
                    namespace=str(payload.get("namespace") or "forward"),
                    hypothesis=str(payload.get("hypothesis") or "paper closed cycle"),
                    realized_pnl=Decimal(str(payload.get("realized_pnl") or "0")),
                    maximum_adverse_excursion=Decimal(str(payload.get("mae") or "0")),
                    maximum_favorable_excursion=Decimal(str(payload.get("mfe") or "0")),
                    fees=Decimal(str(payload.get("fees") or "0")),
                    exit_reason=str(payload.get("exit_reason") or "TAKE_PROFIT"),
                    regime_tags=(str(payload.get("symbol") or "UNKNOWN"),),
                )
                reflection = self._engine.create(outcome)
                with self._repo.database.transaction() as connection:
                    self._repo.record_reflection(
                        reflection_id=reflection.identifier,
                        trade_id=trade_id,
                        namespace=reflection.namespace,
                        lesson_code=reflection.lesson_code,
                        lesson=reflection.lesson,
                        regime_tags=list(reflection.regime_tags),
                        net_pnl=reflection.net_pnl,
                        fee_drag=reflection.fee_drag,
                        mae=reflection.maximum_adverse_excursion,
                        mfe=reflection.maximum_favorable_excursion,
                        exit_reason=reflection.exit_reason,
                        payload=payload,
                        connection=connection,
                    )
                    self._repo.mark_outbox(connection, trade_id, "done")
                drained += 1
            except Exception:
                continue
        return drained
