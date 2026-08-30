"""Closed-paper-trade → one durable reflection. Idempotent on trade_id."""

from __future__ import annotations

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

    def record_closed_trade(
        self,
        trade: ClosedPaperTrade,
        *,
        trade_id: str,
        symbol: str,
        genome_id: str | None = None,
        hypothesis: str = "paper closed cycle",
    ) -> str | None:
        if self.already_recorded(trade_id):
            return None
        fees = trade.entry_fill.fee + trade.exit_fill.fee
        outcome = TradeOutcome(
            trade_id=trade_id,
            namespace="forward",
            hypothesis=hypothesis,
            realized_pnl=trade.realized_pnl,
            maximum_adverse_excursion=Decimal("0"),
            maximum_favorable_excursion=Decimal("0"),
            fees=fees,
            exit_reason=trade.exit_reason.value,
            regime_tags=(symbol,),
        )
        reflection = self._engine.create(outcome)
        self._bank.record_reflection(reflection)
        return reflection.identifier
