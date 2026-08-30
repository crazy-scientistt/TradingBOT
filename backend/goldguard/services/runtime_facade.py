"""Single control surface. Legacy PAXG and Autonomous never both execute."""

from __future__ import annotations

from goldguard.domain.enums import StrategyMode
from goldguard.domain.profile import AutonomousProfile
from goldguard.services.autonomous_runtime import AutonomousRuntime
from goldguard.services.runtime import RuntimeStatus, TradingRuntime


class RuntimeFacade:
    def __init__(
        self,
        *,
        profile: AutonomousProfile,
        legacy: TradingRuntime,
        autonomous: AutonomousRuntime | None = None,
    ) -> None:
        self._profile = profile
        self._legacy = legacy
        self._autonomous = autonomous

    @property
    def owner(self) -> StrategyMode:
        return self._profile.strategy_mode

    @property
    def legacy(self) -> TradingRuntime:
        return self._legacy

    @property
    def autonomous(self) -> AutonomousRuntime | None:
        return self._autonomous

    def _active(self) -> TradingRuntime | AutonomousRuntime:
        if self.owner is StrategyMode.AUTONOMOUS and self._autonomous is not None:
            return self._autonomous
        return self._legacy

    def apply_profile(self, profile: AutonomousProfile) -> None:
        if profile.strategy_mode != self._profile.strategy_mode:
            status = self.status()
            if status.has_position or (status.running and not status.paused):
                raise RuntimeError(
                    "execution owner can change only while paper is flat and paused"
                )
        self._profile = profile
        if self._autonomous is not None:
            self._autonomous.apply_profile(profile)

    def start(self) -> None:
        self._active().start()

    def pause(self) -> None:
        self._active().pause()

    def stop(self) -> None:
        self._active().stop()

    def shutdown(self) -> None:
        self._legacy.shutdown()
        if self._autonomous is not None:
            self._autonomous.shutdown()

    def status(self) -> RuntimeStatus:
        return self._active().status()

    def is_legacy_owner(self) -> bool:
        return self.owner is StrategyMode.LEGACY or self._autonomous is None

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
        if self.owner is StrategyMode.LEGACY:
            scopes = ["SPOT:PAXGUSDT"]
        else:
            if self._profile.spot_enabled:
                scopes.extend(f"SPOT:{item}" for item in self._profile.spot_pairs)
            if self._profile.futures_enabled:
                scopes.extend(f"FUTURES:{item}" for item in self._profile.futures_pairs)
        runtime = self.status()
        return {
            "execution_owner": self.owner.value,
            "scopes": scopes,
            "running": runtime.running,
            "paused": runtime.paused,
            "active_genome_id": genome_id,
            "reflection_count": reflection_count,
            "dataset_status": dataset_status,
            "hermes_status": hermes_status,
            "live_enabled": live_enabled,
            "canary_stage": None,
        }
