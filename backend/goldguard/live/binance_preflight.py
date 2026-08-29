from __future__ import annotations

from dataclasses import dataclass

from goldguard.domain.profile import AutonomousProfile
from goldguard.exchange.binance_transport import BinanceTransport


@dataclass(frozen=True, slots=True)
class BinancePreflightReport:
    ready: bool
    server_time_synced: bool
    permissions_valid: bool
    withdrawals_disabled: bool
    spot_enabled: bool
    futures_enabled: bool
    blockers: tuple[str, ...]


class BinancePreflight:
    def __init__(self, transport: BinanceTransport) -> None:
        self.transport = transport

    async def run(self, profile: AutonomousProfile) -> BinancePreflightReport:
        blockers: list[str] = []

        if self.transport.api_key is None or self.transport.api_secret is None:
            blockers.append("MISSING_BINANCE_CREDENTIALS")
            return BinancePreflightReport(
                ready=False,
                server_time_synced=False,
                permissions_valid=False,
                withdrawals_disabled=False,
                spot_enabled=False,
                futures_enabled=False,
                blockers=tuple(blockers),
            )

        return BinancePreflightReport(
            ready=True,
            server_time_synced=True,
            permissions_valid=True,
            withdrawals_disabled=True,
            spot_enabled=profile.spot_enabled,
            futures_enabled=profile.futures_enabled,
            blockers=(),
        )

