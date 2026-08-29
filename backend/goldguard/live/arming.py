from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from goldguard.live.models import (
    ArmingState,
    ArmingStatus,
    ArmRequest,
    LiveArmingRejected,
    expected_confirmation,
)
from goldguard.security.models import AuthPrincipal
from goldguard.security.service import AuthService
from goldguard.services.preflight import PreflightReport
from goldguard.storage.database import Database
from goldguard.storage.profile_repository import ProfileRepository


class ArmingService:
    def __init__(
        self,
        database: Database,
        profile_repository: ProfileRepository,
        auth_service: AuthService,
    ) -> None:
        self.database = database
        self.profile_repository = profile_repository
        self.auth_service = auth_service

    def get_state(self) -> ArmingState:
        with self.database.connect() as conn:
            row = conn.execute(
                "SELECT status, profile_hash, expected_equity_usdt, armed_at, armed_by "
                "FROM live_arming_state WHERE id = 1"
            ).fetchone()
            if row is None:
                return ArmingState(
                    status=ArmingStatus.DISARMED,
                    profile_hash=None,
                    expected_equity_usdt=None,
                    armed_at=None,
                    armed_by=None,
                    new_entries_allowed=False,
                )
            status = ArmingStatus(str(row["status"]))
            equity = (
                Decimal(str(row["expected_equity_usdt"]))
                if row["expected_equity_usdt"] is not None
                else None
            )
            return ArmingState(
                status=status,
                profile_hash=(
                    str(row["profile_hash"]) if row["profile_hash"] is not None else None
                ),
                expected_equity_usdt=equity,
                armed_at=str(row["armed_at"]) if row["armed_at"] is not None else None,
                armed_by=str(row["armed_by"]) if row["armed_by"] is not None else None,
                new_entries_allowed=(status == ArmingStatus.ARMED_READY),
            )

    def arm(
        self,
        request: ArmRequest,
        principal: AuthPrincipal,
        report: PreflightReport,
    ) -> ArmingState:
        # 1. Require recent TOTP
        try:
            self.auth_service.require_recent_totp(
                principal.session_id, max_age=timedelta(minutes=5)
            )
        except Exception as exc:
            raise LiveArmingRejected("recent 2FA verification is required") from exc

        # 2. Check preflight report for failed gates
        for check in report.checks:
            if check.status == "fail":
                raise LiveArmingRejected(
                    f"preflight gate failed: {check.id} - {check.detail}"
                )

        if not report.ready:
            raise LiveArmingRejected("preflight report is not ready")

        # 3. Check active profile version
        active = self.profile_repository.active()
        if active is None:
            raise LiveArmingRejected("no active profile is configured")
        if active.hash != request.profile_version:
            raise LiveArmingRejected(
                f"profile version mismatch: active={active.hash} "
                f"requested={request.profile_version}"
            )

        # 4. Check typed confirmation string
        expected = expected_confirmation(active.profile)
        if request.confirmation.strip() != expected.strip():
            raise LiveArmingRejected(
                f"confirmation string mismatch: expected {expected!r}, got {request.confirmation!r}"
            )

        # 5. Persist live arming state
        now = datetime.now(UTC).isoformat()
        with self.database.transaction() as tx:
            tx.execute(
                "UPDATE live_arming_state "
                "SET status = 'armed_ready', profile_hash = ?, expected_equity_usdt = ?, "
                "armed_at = ?, armed_by = ? WHERE id = 1",
                (
                    active.hash,
                    str(request.expected_equity_usdt),
                    now,
                    principal.actor,
                ),
            )
            tx.execute(
                "INSERT INTO security_events "
                "(event_type, actor, correlation_id, metadata, created_at) "
                "VALUES (?, ?, ?, ?, ?)",
                (
                    "live_armed",
                    principal.actor,
                    principal.correlation_id,
                    json.dumps(
                        {
                            "profile_hash": active.hash,
                            "expected_equity_usdt": str(request.expected_equity_usdt),
                            "outcome": "success",
                        },
                        sort_keys=True,
                    ),
                    now,
                ),
            )

        return ArmingState(
            status=ArmingStatus.ARMED_READY,
            profile_hash=active.hash,
            expected_equity_usdt=request.expected_equity_usdt,
            armed_at=now,
            armed_by=principal.actor,
            new_entries_allowed=True,
        )

    def disarm(
        self,
        principal: AuthPrincipal | None = None,
        reason: str = "manual_disarm",
    ) -> ArmingState:
        now = datetime.now(UTC).isoformat()
        actor = principal.actor if principal is not None else "system"
        correlation = principal.correlation_id if principal is not None else "disarm"

        with self.database.transaction() as tx:
            tx.execute(
                "UPDATE live_arming_state "
                "SET status = 'disarmed', profile_hash = NULL, expected_equity_usdt = NULL, "
                "armed_at = NULL, armed_by = NULL WHERE id = 1"
            )
            tx.execute(
                "INSERT INTO security_events "
                "(event_type, actor, correlation_id, metadata, created_at) "
                "VALUES (?, ?, ?, ?, ?)",
                (
                    "live_disarmed",
                    actor,
                    correlation,
                    json.dumps({"reason": reason, "outcome": "success"}, sort_keys=True),
                    now,
                ),
            )

        return ArmingState(
            status=ArmingStatus.DISARMED,
            profile_hash=None,
            expected_equity_usdt=None,
            armed_at=None,
            armed_by=None,
            new_entries_allowed=False,
        )

    def on_restart(self) -> ArmingState:
        now = datetime.now(UTC).isoformat()
        with self.database.transaction() as tx:
            row = tx.execute(
                "SELECT status, profile_hash, expected_equity_usdt, armed_at, armed_by "
                "FROM live_arming_state WHERE id = 1"
            ).fetchone()
            if row is None or str(row["status"]) == "disarmed":
                return ArmingState(
                    status=ArmingStatus.DISARMED,
                    profile_hash=None,
                    expected_equity_usdt=None,
                    armed_at=None,
                    armed_by=None,
                    new_entries_allowed=False,
                )

            tx.execute(
                "UPDATE live_arming_state "
                "SET status = 'armed_pending_reconciliation' "
                "WHERE id = 1 AND status != 'disarmed'"
            )
            tx.execute(
                "INSERT INTO security_events "
                "(event_type, actor, correlation_id, metadata, created_at) "
                "VALUES (?, ?, ?, ?, ?)",
                (
                    "live_restart_reconciliation_required",
                    "system",
                    "restart-reconcile",
                    json.dumps(
                        {"profile_hash": str(row["profile_hash"]), "outcome": "pending"},
                        sort_keys=True,
                    ),
                    now,
                ),
            )

            equity = (
                Decimal(str(row["expected_equity_usdt"]))
                if row["expected_equity_usdt"] is not None
                else None
            )
            return ArmingState(
                status=ArmingStatus.ARMED_PENDING_RECONCILIATION,
                profile_hash=str(row["profile_hash"]),
                expected_equity_usdt=equity,
                armed_at=str(row["armed_at"]),
                armed_by=str(row["armed_by"]),
                new_entries_allowed=False,
            )


_arming_service: ArmingService | None = None


def configure_arming_service(service: ArmingService) -> None:
    global _arming_service
    _arming_service = service


def get_arming_service() -> ArmingService:
    if _arming_service is None:
        raise RuntimeError("arming service is not configured")
    return _arming_service

