from __future__ import annotations

import contextlib
from collections.abc import Iterator
from pathlib import Path

import pyotp
import pytest
from fastapi.testclient import TestClient
from goldguard.domain.profile import default_autonomous_profile
from goldguard.live.models import expected_confirmation
from goldguard.services.settings_service import get_settings_service
from goldguard.web.auth_dependencies import get_auth_service
from pydantic import SecretStr


@pytest.fixture
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    monkeypatch.setenv("GOLDGUARD_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("GOLDGUARD_ENVIRONMENT", "test")
    monkeypatch.setenv("GOLDGUARD_MARKET_INGESTION_ENABLED", "false")
    monkeypatch.setenv("GOLDGUARD_GATEWAY_BASE_URL", "")
    monkeypatch.setenv("OPENCODEX_BASE_URL", "")
    monkeypatch.setenv("GOLDGUARD_PAPER_STARTING_BALANCE", "10000")

    from goldguard.web import app as app_module

    with TestClient(app_module.app) as test_client:
        service = get_auth_service()
        with contextlib.suppress(Exception):
            service.bootstrap_admin(
                SecretStr("correct-admin-password"),
                SecretStr("JBSWY3DPEHPK3PXP"),
            )
        settings_service = get_settings_service()
        if settings_service._repository.active() is None:
            settings_service._repository.activate(
                default_autonomous_profile(), actor="admin", correlation_id="init-test"
            )
        yield test_client


def login_full_auth(client: TestClient) -> dict[str, str]:
    login_res = client.post("/api/auth/login", json={"password": "correct-admin-password"})
    assert login_res.status_code == 200
    totp = pyotp.TOTP("JBSWY3DPEHPK3PXP")
    totp_res = client.post("/api/auth/totp", json={"code": totp.now()})
    assert totp_res.status_code == 200
    csrf_token = totp_res.json()["csrf_token"]
    return {"X-CSRF-Token": csrf_token}


def test_preflight_route(client: TestClient) -> None:
    res = client.get("/api/preflight")
    assert res.status_code == 200
    data = res.json()
    assert "ready" in data
    assert "checks" in data
    assert len(data["checks"]) >= 5


def test_arm_and_disarm_flow(client: TestClient) -> None:
    headers = login_full_auth(client)
    profile_res = client.get("/api/settings/profile")
    assert profile_res.status_code == 200
    profile_data = profile_res.json()
    profile_hash = profile_data["hash"]

    active = get_settings_service()._repository.active()
    assert active is not None
    confirmation = expected_confirmation(active.profile)

    # 1. Arm live
    arm_res = client.post(
        "/api/live/arm",
        json={
            "confirmation": confirmation,
            "profile_version": profile_hash,
            "expected_equity_usdt": "10000.00",
        },
        headers=headers,
    )
    assert arm_res.status_code == 200
    arm_data = arm_res.json()
    assert arm_data["status"] == "armed_ready"
    assert arm_data["new_entries_allowed"] is True

    # 2. Disarm
    disarm_res = client.post("/api/live/disarm", headers=headers)
    assert disarm_res.status_code == 200
    disarm_data = disarm_res.json()
    assert disarm_data["status"] == "disarmed"
    assert disarm_data["new_entries_allowed"] is False

