from dataclasses import dataclass
from datetime import datetime, timedelta

from goldguard.context.models import ContextSnapshot
from goldguard.domain.enums import ChecklistAction


@dataclass(frozen=True)
class ChecklistInputs:
    context: ContextSnapshot
    now: datetime
    data_healthy: bool
    exchange_normal: bool
    liquidity_acceptable: bool
    regime_clear: bool
    deterministic_setup: bool
    complete_trade_plan: bool
    risk_budget_available: bool
    cooldown_clear: bool
    event_blackout: bool


@dataclass(frozen=True)
class ChecklistResult:
    action: ChecklistAction
    reason_codes: tuple[str, ...]


class ProfessionalChecklist:
    def __init__(self, max_context_age: timedelta = timedelta(minutes=30)) -> None:
        self.max_context_age = max_context_age

    def evaluate(self, inputs: ChecklistInputs) -> ChecklistResult:
        reason = self._first_block(inputs)
        if reason is not None:
            return ChecklistResult(ChecklistAction.HOLD, (reason,))
        return ChecklistResult(ChecklistAction.PASS, ("PRO_CHECKLIST_PASSED",))

    def _first_block(self, inputs: ChecklistInputs) -> str | None:
        if not inputs.data_healthy:
            return "DATA_UNHEALTHY"
        if not inputs.exchange_normal:
            return "EXCHANGE_UNHEALTHY"
        if not inputs.liquidity_acceptable:
            return "LIQUIDITY_UNACCEPTABLE"
        if not inputs.regime_clear:
            return "REGIME_UNCLEAR"
        if not inputs.deterministic_setup:
            return "NO_DETERMINISTIC_SETUP"
        if not inputs.complete_trade_plan:
            return "INCOMPLETE_TRADE_PLAN"
        if not inputs.risk_budget_available:
            return "RISK_BUDGET_UNAVAILABLE"
        if not inputs.cooldown_clear:
            return "COOLDOWN_ACTIVE"
        if inputs.event_blackout:
            return "MACRO_EVENT_BLACKOUT"
        if inputs.now - inputs.context.fetched_at > self.max_context_age:
            return "STALE_CONTEXT"
        if inputs.context.conflict_level == "HIGH":
            return "CONTEXT_CONFLICT_HIGH"
        if not inputs.context.items or not inputs.context.sources:
            return "UNCITED_CONTEXT"
        for item in inputs.context.items:
            if not item.source_indexes or any(
                index < 0 or index >= len(inputs.context.sources) for index in item.source_indexes
            ):
                return "UNCITED_CONTEXT"
        if any(item.contradictory for item in inputs.context.items):
            return "CONTRADICTORY_CONTEXT"
        if inputs.context.prompt_injection_suspected:
            return "UNTRUSTED_CONTEXT_INSTRUCTIONS"
        return None
