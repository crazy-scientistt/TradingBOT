from datetime import UTC, datetime
from decimal import Decimal

from goldguard.ai.gemini import AiAssessment
from goldguard.broker.paper import PaperBroker
from goldguard.context.playbook import ChecklistResult
from goldguard.domain.enums import AiDecision, CandidateAction, ChecklistAction
from goldguard.domain.models import Quote, TradePlan
from goldguard.risk.engine import RiskDecision
from goldguard.services.trading import TradingService
from goldguard.strategy.engine import StrategyResult


def test_entry_pipeline_requires_strategy_checklist_ai_and_risk_approval() -> None:
    broker = PaperBroker(Decimal("100"), Decimal("0.001"), Decimal("0.0002"))
    service = TradingService(broker)
    strategy = StrategyResult(CandidateAction.ENTRY_CANDIDATE, ("SETUP",))
    checklist = ChecklistResult(ChecklistAction.PASS, ("PRO_CHECKLIST_PASSED",))
    ai = AiAssessment(
        decision=AiDecision.APPROVE_ENTRY,
        confidence=72,
        reason_codes=("TREND_ALIGNED",),
        rationale="approved",
        memory_refs=(),
        prompt_hash="hash",
        model="gemini-2.5-flash",
    )
    plan = TradePlan(
        entry=Decimal("2500"),
        stop=Decimal("2487.50"),
        target=Decimal("2525"),
        quantity=Decimal("0.02"),
        risk_amount=Decimal("0.25"),
        expected_fees=Decimal("0.10"),
    )
    risk = RiskDecision(True, ("RISK_APPROVED",), plan)
    current_quote = Quote(
        bid=Decimal("2499.80"),
        ask=Decimal("2500"),
        observed_at=datetime(2026, 8, 26, tzinfo=UTC),
    )

    outcome = service.execute_entry(
        strategy=strategy,
        checklist=checklist,
        ai=ai,
        risk=risk,
        quote=current_quote,
        client_order_id="decision-1-entry",
    )

    assert outcome.executed is True
    assert outcome.reason_codes == ("PAPER_ENTRY_FILLED",)
    assert broker.position is not None


def test_any_failed_gate_holds_without_touching_wallet() -> None:
    broker = PaperBroker(Decimal("100"), Decimal("0.001"), Decimal("0.0002"))
    outcome = TradingService(broker).execute_entry(
        strategy=StrategyResult(CandidateAction.NO_ACTION, ("NO_SETUP",)),
        checklist=ChecklistResult(ChecklistAction.PASS, ("PRO_CHECKLIST_PASSED",)),
        ai=AiAssessment(
            decision=AiDecision.APPROVE_ENTRY,
            confidence=90,
            reason_codes=("TREND_ALIGNED",),
            rationale="approved",
            memory_refs=(),
            prompt_hash="hash",
            model="gemini-2.5-flash",
        ),
        risk=RiskDecision(False, ("NO_RISK_PLAN",), None),
        quote=Quote(
            bid=Decimal("2499"),
            ask=Decimal("2500"),
            observed_at=datetime(2026, 8, 26, tzinfo=UTC),
        ),
        client_order_id="decision-1-entry",
    )

    assert outcome.executed is False
    assert outcome.reason_codes == ("NO_DETERMINISTIC_ENTRY",)
    assert broker.cash == Decimal("100")
    assert broker.position is None
