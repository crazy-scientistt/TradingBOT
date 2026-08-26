from dataclasses import dataclass

from goldguard.ai.gemini import AiAssessment
from goldguard.broker.base import Broker, PaperFill
from goldguard.context.playbook import ChecklistResult
from goldguard.domain.enums import AiDecision, CandidateAction, ChecklistAction
from goldguard.domain.models import Quote
from goldguard.risk.engine import RiskDecision
from goldguard.strategy.engine import StrategyResult


@dataclass(frozen=True)
class EntryOutcome:
    executed: bool
    reason_codes: tuple[str, ...]
    fill: PaperFill | None = None


class TradingService:
    """Fail-closed entry coordinator; every gate must approve in order."""

    def __init__(self, broker: Broker) -> None:
        self._broker = broker

    def execute_entry(
        self,
        *,
        strategy: StrategyResult,
        checklist: ChecklistResult,
        ai: AiAssessment,
        risk: RiskDecision,
        quote: Quote,
        client_order_id: str,
    ) -> EntryOutcome:
        if strategy.action is not CandidateAction.ENTRY_CANDIDATE:
            return EntryOutcome(False, ("NO_DETERMINISTIC_ENTRY",))
        if checklist.action is not ChecklistAction.PASS:
            return EntryOutcome(False, checklist.reason_codes)
        if ai.decision is not AiDecision.APPROVE_ENTRY:
            return EntryOutcome(False, ai.reason_codes)
        if not risk.approved or risk.plan is None:
            return EntryOutcome(False, risk.reason_codes or ("RISK_NOT_APPROVED",))

        fill = self._broker.open_long(
            risk.plan,
            quote,
            client_order_id=client_order_id,
        )
        return EntryOutcome(True, ("PAPER_ENTRY_FILLED",), fill)
