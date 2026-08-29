from __future__ import annotations

from decimal import Decimal
from pathlib import Path

import pyotp
import pytest
from goldguard.domain.profile import AutonomousProfile, default_autonomous_profile
from goldguard.live.arming import ArmingService
from goldguard.live.models import (
    ArmingStatus,
    ArmRequest,
    LiveArmingRejected,
    expected_confirmation,
)
from goldguard.security.models import AuthPrincipal
from goldguard.security.service import AuthService
from goldguard.services.preflight import PreflightCheck, PreflightReport, PreflightService
from goldguard.storage.database import Database
from goldguard.storage.profile_repository import ProfileRepository
from pydantic import SecretStr


@pytest.fixture
def database(tmp_path: Path) -> Database:
    db = Database(tmp_path / "live_arming_test.db")
    db.migrate()
    return db


@pytest.fixture
def profile_repository(database: Database) -> ProfileRepository:
    return ProfileRepository(database)


@pytest.fixture
def auth_service(database: Database) -> AuthService:
    service = AuthService(database, production=False)
    service.bootstrap_admin(
        SecretStr("correct-admin-password"),
        SecretStr("JBSWY3DPEHPK3PXP"),
    )
    return service


@pytest.fixture
def arming_service(
    database: Database,
    profile_repository: ProfileRepository,
    auth_service: AuthService,
) -> ArmingService:
    return ArmingService(database, profile_repository, auth_service)


@pytest.fixture
def active_profile(profile_repository: ProfileRepository) -> AutonomousProfile:
    profile = default_autonomous_profile()
    profile_repository.activate(profile, actor="admin", correlation_id="init-test")
    return profile


@pytest.fixture
def passing_report(active_profile: AutonomousProfile) -> PreflightReport:
    return PreflightReport(
        ready=True,
        checks=tuple(
            PreflightCheck(id=gate_id, label=label, status="pass", detail=detail)
            for gate_id, label, detail in PreflightService.GATE_DEFINITIONS
        ),
    )


@pytest.fixture
def recent_totp_principal(auth_service: AuthService) -> AuthPrincipal:
    tokens = auth_service.login(
        SecretStr("correct-admin-password"), ip="127.0.0.1", user_agent="test"
    )
    totp = pyotp.TOTP("JBSWY3DPEHPK3PXP")
    session = auth_service.verify_totp(tokens.session_id, totp.now())
    return AuthPrincipal(
        username="admin",
        session_id=session.session_id,
        ip="127.0.0.1",
        user_agent="test",
        last_totp_at=session.last_totp_at,
        correlation_id="test-corr",
    )


def valid_arm_request(profile_repository: ProfileRepository) -> ArmRequest:
    active = profile_repository.active()
    assert active is not None
    return ArmRequest(
        confirmation=expected_confirmation(active.profile),
        profile_version=active.hash,
        expected_equity_usdt=Decimal("10000.00"),
    )


@pytest.mark.parametrize(
    "failed_gate",
    [
        "paper_qualification",
        "binance_permissions",
        "withdrawals_disabled",
        "market_freshness",
        "database_integrity",
        "opencodex_route",
        "hermes_route",
        "telegram_critical",
        "reconciliation",
    ],
)
def test_live_arm_rejects_each_failed_gate(
    arming_service: ArmingService,
    profile_repository: ProfileRepository,
    active_profile: AutonomousProfile,
    passing_report: PreflightReport,
    recent_totp_principal: AuthPrincipal,
    failed_gate: str,
) -> None:
    report = passing_report.with_failure(failed_gate)
    request = valid_arm_request(profile_repository)
    with pytest.raises(LiveArmingRejected, match=failed_gate):
        arming_service.arm(request, recent_totp_principal, report)


def test_restart_preserves_intent_but_blocks_entries_until_reconciled(
    arming_service: ArmingService,
    profile_repository: ProfileRepository,
    active_profile: AutonomousProfile,
    passing_report: PreflightReport,
    recent_totp_principal: AuthPrincipal,
) -> None:
    request = valid_arm_request(profile_repository)
    armed = arming_service.arm(request, recent_totp_principal, passing_report)
    assert armed.status == ArmingStatus.ARMED_READY
    assert armed.new_entries_allowed is True

    restarted = arming_service.on_restart()
    assert restarted.status == ArmingStatus.ARMED_PENDING_RECONCILIATION
    assert restarted.new_entries_allowed is False


def test_not_ready_report_cannot_arm_even_without_failed_checks(
    arming_service: ArmingService,
    profile_repository: ProfileRepository,
    active_profile: AutonomousProfile,
    recent_totp_principal: AuthPrincipal,
) -> None:
    report = PreflightReport(
        ready=False,
        checks=tuple(
            PreflightCheck(id=gate_id, label=label, status="warn", detail="pending")
            for gate_id, label, _ in PreflightService.GATE_DEFINITIONS
        ),
    )

    with pytest.raises(LiveArmingRejected, match="not ready"):
        arming_service.arm(
            valid_arm_request(profile_repository),
            recent_totp_principal,
            report,
        )
