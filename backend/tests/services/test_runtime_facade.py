from goldguard.domain.enums import StrategyMode
from goldguard.domain.profile import default_autonomous_profile
from goldguard.services.runtime_facade import RuntimeFacade


class _Legacy:
    def status(self):
        from types import SimpleNamespace
        from goldguard.domain.enums import BotState

        return SimpleNamespace(
            state=BotState.PAPER_READY,
            running=False,
            paused=True,
            halted=False,
            has_position=False,
            degraded_reasons=(),
        )

    def start(self) -> None:
        return None

    def pause(self) -> None:
        return None

    def stop(self) -> None:
        return None

    def shutdown(self) -> None:
        return None


def test_autonomous_default_lists_spot_universe() -> None:
    facade = RuntimeFacade(profile=default_autonomous_profile(), legacy=_Legacy())  # type: ignore[arg-type]
    assert facade.owner is StrategyMode.AUTONOMOUS
    described = facade.describe(
        genome_id="g1",
        reflection_count=0,
        dataset_status="UNKNOWN",
        hermes_status="configured",
        live_enabled=False,
    )
    assert described["live_enabled"] is False
    assert "SPOT:ETHUSDT" in described["scopes"]
    assert described["execution_owner"] == "autonomous"
