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
    BotState.DISARMED: frozenset(
        {BotState.PAPER_READY, BotState.LIVE_READ_ONLY, BotState.RECOVERY_REQUIRED}
    ),
    BotState.PAPER_READY: frozenset(
        {BotState.RUNNING_FLAT, BotState.DISARMED, BotState.DATA_HALTED}
    ),
    BotState.LIVE_READ_ONLY: frozenset(
        {BotState.RUNNING_FLAT, BotState.DISARMED, BotState.RECOVERY_REQUIRED}
    ),
    BotState.RUNNING_FLAT: frozenset(
        {
            BotState.RUNNING_OPEN,
            BotState.COOLDOWN,
            BotState.RISK_HALTED,
            BotState.DATA_HALTED,
            BotState.EMERGENCY_STOPPED,
            BotState.DISARMED,
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
        }
    ),
    BotState.COOLDOWN: frozenset(
        {BotState.RUNNING_FLAT, BotState.RISK_HALTED, BotState.DATA_HALTED, BotState.DISARMED}
    ),
    BotState.RISK_HALTED: frozenset(
        {BotState.DISARMED, BotState.EMERGENCY_STOPPED, BotState.RECOVERY_REQUIRED}
    ),
    BotState.DATA_HALTED: frozenset(
        {BotState.DISARMED, BotState.RECOVERY_REQUIRED, BotState.EMERGENCY_STOPPED}
    ),
    BotState.RECOVERY_REQUIRED: frozenset({BotState.DISARMED, BotState.EMERGENCY_STOPPED}),
    BotState.EMERGENCY_STOPPED: frozenset({BotState.DISARMED}),
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
