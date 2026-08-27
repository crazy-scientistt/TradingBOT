from dataclasses import dataclass

from goldguard.domain.enums import BotState


class TransitionError(ValueError):
    pass


@dataclass(frozen=True)
class StateTransition:
    from_state: BotState
    to_state: BotState
    reason: str


ALLOWED_TRANSITIONS: dict[BotState, frozenset[BotState]] = {
    BotState.BOOTING: frozenset(
        {BotState.DISARMED, BotState.RECOVERY_REQUIRED, BotState.EMERGENCY_STOPPED}
    ),
    # Emergency stop is reachable from every non-terminal state: a user pressing the
    # halt control must never be refused because the bot happens to be idle.
    BotState.DISARMED: frozenset(
        {
            BotState.PAPER_READY,
            BotState.LIVE_READ_ONLY,
            BotState.RECOVERY_REQUIRED,
            BotState.EMERGENCY_STOPPED,
        }
    ),
    BotState.PAPER_READY: frozenset(
        {
            BotState.RUNNING_FLAT,
            BotState.RUNNING_OPEN,
            BotState.DISARMED,
            BotState.DATA_HALTED,
            BotState.EMERGENCY_STOPPED,
        }
    ),
    BotState.LIVE_READ_ONLY: frozenset(
        {
            BotState.RUNNING_FLAT,
            BotState.DISARMED,
            BotState.RECOVERY_REQUIRED,
            BotState.EMERGENCY_STOPPED,
        }
    ),
    BotState.RUNNING_FLAT: frozenset(
        {
            BotState.RUNNING_OPEN,
            BotState.COOLDOWN,
            BotState.RISK_HALTED,
            BotState.DATA_HALTED,
            BotState.EMERGENCY_STOPPED,
            BotState.DISARMED,
            BotState.RESEARCH_ACTIVE,
            BotState.AUTONOMY_SUSPENDED,
            BotState.QUARANTINE,
        }
    ),
    BotState.RUNNING_OPEN: frozenset(
        {
            BotState.COOLDOWN,
            BotState.RISK_HALTED,
            BotState.DATA_HALTED,
            BotState.RECOVERY_REQUIRED,
            BotState.EMERGENCY_STOPPED,
            BotState.DISARMED,
            BotState.QUARANTINE,
        }
    ),
    BotState.COOLDOWN: frozenset(
        {
            BotState.RUNNING_FLAT,
            BotState.RUNNING_OPEN,
            BotState.RISK_HALTED,
            BotState.DATA_HALTED,
            BotState.DISARMED,
            BotState.EMERGENCY_STOPPED,
        }
    ),
    BotState.RISK_HALTED: frozenset(
        {BotState.DISARMED, BotState.EMERGENCY_STOPPED, BotState.RECOVERY_REQUIRED}
    ),
    BotState.DATA_HALTED: frozenset(
        {BotState.DISARMED, BotState.RECOVERY_REQUIRED, BotState.EMERGENCY_STOPPED}
    ),
    BotState.RECOVERY_REQUIRED: frozenset({BotState.DISARMED, BotState.EMERGENCY_STOPPED}),
    BotState.EMERGENCY_STOPPED: frozenset({BotState.DISARMED}),
    # Autonomy states
    BotState.RESEARCH_ACTIVE: frozenset(
        {
            BotState.RUNNING_FLAT,
            BotState.AUTONOMY_SUSPENDED,
            BotState.QUARANTINE,
            BotState.DISARMED,
            BotState.EMERGENCY_STOPPED,
        }
    ),
    BotState.AUTONOMY_SUSPENDED: frozenset(
        {
            BotState.RESEARCH_ACTIVE,
            BotState.RUNNING_FLAT,
            BotState.QUARANTINE,
            BotState.DISARMED,
            BotState.EMERGENCY_STOPPED,
        }
    ),
    BotState.QUARANTINE: frozenset(
        {
            BotState.RUNNING_FLAT,
            BotState.DISARMED,
            BotState.RECOVERY_REQUIRED,
            BotState.EMERGENCY_STOPPED,
        }
    ),
}


class StateMachine:
    def transition(
        self,
        current: BotState,
        target: BotState,
        *,
        reason: str,
    ) -> StateTransition:
        if target not in ALLOWED_TRANSITIONS[current]:
            raise TransitionError(f"invalid transition {current.value} -> {target.value}")
        if not reason.strip():
            raise TransitionError("state transition requires a reason")
        return StateTransition(current, target, reason)

    def on_restart(self, current: BotState) -> StateTransition:
        return StateTransition(current, BotState.DISARMED, "PROCESS_RESTART_AUTO_DISARM")
