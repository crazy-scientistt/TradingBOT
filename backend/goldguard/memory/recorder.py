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
        }
        try:
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
            if connection is not None:
                self._repo.mark_outbox(connection, trade_id, "done")
            return reflection.identifier
        except Exception as exc:
            self._repo.enqueue_outbox(
                trade_id=trade_id,
                payload=payload,
                error=str(exc),
                connection=connection,
            )
            return None
