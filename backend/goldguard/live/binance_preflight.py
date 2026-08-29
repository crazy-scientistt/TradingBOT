from __future__ import annotations

from dataclasses import dataclass

from goldguard.domain.enums import ProductKind
from goldguard.domain.profile import AutonomousProfile
from goldguard.exchange.binance_transport import BinanceTransport, BinanceTransportError


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
            return BinancePreflightReport(
                ready=False,
                server_time_synced=False,
                permissions_valid=False,
                withdrawals_disabled=False,
                spot_enabled=False,
                futures_enabled=False,
                blockers=("MISSING_BINANCE_CREDENTIALS",),
            )

        try:
            time_payload = await self.transport.request(
                ProductKind.SPOT, "GET", "/api/v3/time", {}, signed=False
            )
            account = await self.transport.request(
                ProductKind.SPOT, "GET", "/api/v3/account", {}, signed=True
            )
            restrictions = await self.transport.request(
                ProductKind.SPOT, "GET", "/sapi/v1/account/apiRestrictions", {}, signed=True
            )
        except BinanceTransportError:
            return BinancePreflightReport(
                ready=False,
                server_time_synced=False,
                permissions_valid=False,
                withdrawals_disabled=False,
                spot_enabled=False,
                futures_enabled=False,
                blockers=("TRANSPORT_UNAVAILABLE",),
            )

        server_time_synced = isinstance(time_payload, dict) and "serverTime" in time_payload
        if not server_time_synced:
            blockers.append("SERVER_TIME_UNSYNCED")

        can_trade = isinstance(account, dict) and bool(account.get("canTrade"))
        if not can_trade:
            blockers.append("TRADING_DISABLED")

        withdrawals_disabled = False
        permissions_valid = False
        spot_perm = False
        fut_perm = False
        if not isinstance(restrictions, dict):
            blockers.append("WITHDRAWALS_UNVERIFIED")
        else:
            enable_withdrawals = bool(restrictions.get("enableWithdrawals"))
            enable_transfer = bool(
                restrictions.get("enableInternalTransfer")
                or restrictions.get("permitsUniversalTransfer")
            )
            withdrawals_disabled = not enable_withdrawals and not enable_transfer
            if not withdrawals_disabled:
                blockers.append("WITHDRAWALS_OR_TRANSFERS_ENABLED")
            spot_perm = bool(restrictions.get("enableSpotAndMarginTrading"))
            fut_perm = bool(restrictions.get("enableFutures"))
            permissions_valid = True
            if profile.spot_enabled and not spot_perm:
                blockers.append("SPOT_PERMISSION_MISSING")
                permissions_valid = False
            if profile.futures_enabled and not fut_perm:
                blockers.append("FUTURES_PERMISSION_MISSING")
                permissions_valid = False

        return BinancePreflightReport(
            ready=len(blockers) == 0,
            server_time_synced=server_time_synced,
            permissions_valid=permissions_valid,
            withdrawals_disabled=withdrawals_disabled,
            spot_enabled=profile.spot_enabled and spot_perm,
            futures_enabled=profile.futures_enabled and fut_perm,
            blockers=tuple(blockers),
        )
