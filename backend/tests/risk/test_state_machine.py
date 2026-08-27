import pytest
from goldguard.domain.enums import BotState
from goldguard.risk.state_machine import StateMachine, TransitionError


@pytest.mark.parametrize(
    ("current", "target"),
    [
        (BotState.BOOTING, BotState.DISARMED),
        (BotState.DISARMED, BotState.PAPER_READY),
        (BotState.DISARMED, BotState.LIVE_READ_ONLY),
        (BotState.PAPER_READY, BotState.RUNNING_FLAT),
        (BotState.PAPER_READY, BotState.RUNNING_OPEN),
        (BotState.RUNNING_FLAT, BotState.RUNNING_OPEN),
        (BotState.RUNNING_OPEN, BotState.COOLDOWN),
        (BotState.COOLDOWN, BotState.RUNNING_FLAT),
        (BotState.COOLDOWN, BotState.RUNNING_OPEN),
        (BotState.RUNNING_FLAT, BotState.RISK_HALTED),
        (BotState.RUNNING_OPEN, BotState.DATA_HALTED),
        (BotState.DATA_HALTED, BotState.RECOVERY_REQUIRED),
        (BotState.RECOVERY_REQUIRED, BotState.DISARMED),
        (BotState.RUNNING_OPEN, BotState.EMERGENCY_STOPPED),
        (BotState.EMERGENCY_STOPPED, BotState.DISARMED),
        # Autonomy state transitions
        (BotState.RUNNING_FLAT, BotState.RESEARCH_ACTIVE),
        (BotState.RESEARCH_ACTIVE, BotState.AUTONOMY_SUSPENDED),
        (BotState.AUTONOMY_SUSPENDED, BotState.RESEARCH_ACTIVE),
        (BotState.RESEARCH_ACTIVE, BotState.QUARANTINE),
        (BotState.RUNNING_OPEN, BotState.QUARANTINE),
        (BotState.QUARANTINE, BotState.RUNNING_FLAT),
        (BotState.QUARANTINE, BotState.DISARMED),
        (BotState.AUTONOMY_SUSPENDED, BotState.DISARMED),
    ],
)
def test_allowed_state_transitions(current: BotState, target: BotState) -> None:
    transition = StateMachine().transition(current, target, reason="test")

    assert transition.from_state is current
    assert transition.to_state is target


def test_live_execution_cannot_be_armed_directly_from_disarmed() -> None:
    with pytest.raises(TransitionError, match=r"DISARMED.*RUNNING_FLAT"):
        StateMachine().transition(BotState.DISARMED, BotState.RUNNING_FLAT, reason="bypass")


def test_restart_always_returns_to_disarmed() -> None:
    for state in BotState:
        if state is BotState.BOOTING:
            continue
        transition = StateMachine().on_restart(state)
        assert transition.to_state is BotState.DISARMED
        assert transition.reason == "PROCESS_RESTART_AUTO_DISARM"
