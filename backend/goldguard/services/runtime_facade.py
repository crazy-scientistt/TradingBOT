"""Single control surface. Legacy PAXG and Autonomous never both execute."""

from __future__ import annotations

from dataclasses import dataclass

from goldguard.domain.enums import StrategyMode
from goldguard.domain.profile import AutonomousProfile
from goldguard.services.runtime import RuntimeStatus, TradingRuntime
from goldguard.services.runtime_supervisor import RuntimeSupervisor


@dataclass
class FacadeStatus:
    owner: str
    running: bool
    paused: bool
    scopes: tuple[str, ...]
    genome_id: str | None
    reflection_count: int
    dataset_status: str
    hermes_status: str
    live_enabled: bool
    legacy: RuntimeStatus | None


class RuntimeFacade:
    def __init__(
        self,
        *,
        profile: AutonomousProfile,
        legacy: TradingRuntime,
        autonomous: RuntimeSupervisor | None = None,
    ) -> None:
        self._profile = profile
        self._legacy = legacy
        self._autonomous = autonomous
        self._paused = True

    @property
    def owner(self) -> StrategyMode:
        return self._profile.strategy_mode

    @property
    def legacy(self) -> TradingRuntime:
        return self._legacy

    def apply_profile(self, profile: AutonomousProfile) -> None:
        if profile.strategy_mode != self._profile.strategy_mode:
            status = self._legacy.status()
            if status.has_position or (status.running and not status.paused):
                raise RuntimeError("execution owner can change only while paper is flat and paused")
        self._profile = profile
        if self._autonomous is not None:
            self._autonomous.apply_profile(profile)

    def start(self) -> None:
        self._paused = False
        self._legacy.start()

    def pause(self) -> None:
        self._paused = True
        self._legacy.pause()
        if self._autonomous is not None:
            self._autonomous._coordinator.pause_entries()

    def stop(self) -> None:
        self._paused = True
        self._legacy.stop()

    def shutdown(self) -> None:
        self._legacy.shutdown()

    def status(self) -> RuntimeStatus:
        return self._legacy.status()

    def is_legacy_symbol_only(self, symbol: str) -> bool:
        if self.owner is StrategyMode.LEGACY:
            return symbol == "PAXGUSDT"
        return True

    def describe(
        self,
        *,
        genome_id: str | None,
        reflection_count: int,
        dataset_status: str,
        hermes_status: str,
        live_enabled: bool,
    ) -> dict[str, object]:
        scopes: list[str] = []
        if self._profile.spot_enabled:
            scopes.extend(f"SPOT:{item}" for item in self._profile.spot_pairs)
        if self._profile.futures_enabled:
            scopes.extend(f"FUTURES:{item}" for item in self._profile.futures_pairs)
        runtime = self._legacy.status()
        return {
            "execution_owner": self.owner.value,
            "scopes": scopes if self.owner is StrategyMode.AUTONOMOUS else ["SPOT:PAXGUSDT"],
            "running": runtime.running,
            "paused": runtime.paused,
            "active_genome_id": genome_id,
            "reflection_count": reflection_count,
            "dataset_status": dataset_status,
            "hermes_status": hermes_status,
            "live_enabled": live_enabled,
            "canary_stage": None,
        }
