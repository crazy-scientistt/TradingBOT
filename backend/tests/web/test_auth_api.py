from __future__ import annotations

import contextlib
from collections.abc import Iterator
from pathlib import Path

import pyotp
import pytest
from fastapi.testclient import TestClient
from goldguard.web.auth_dependencies import COOKIE_NAME, get_auth_service
from pydantic import SecretStr


@pytest.fixture
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    monkeypatch.setenv("GOLDGUARD_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("GOLDGUARD_ENVIRONMENT", "test")
    monkeypatch.setenv("GOLDGUARD_MARKET_INGESTION_ENABLED", "false")
    monkeypatch.setenv("GOLDGUARD_GATEWAY_BASE_URL", "")
    monkeypatch.setenv("OPENCODEX_BASE_URL", "")

    from goldguard.web import app as app_module

    with TestClient(app_module.app) as test_client:
        service = get_auth_service()
        with contextlib.suppress(Exception):
            service.bootstrap_admin(
                SecretStr("correct-admin-password"),
                SecretStr("JBSWY3DPEHPK3PXP"),
            )
        yield test_client


def test_auth_flow_login_totp_session_logout(client: TestClient) -> None:
    session_before = client.get("/api/auth/session")
    assert session_before.status_code == 200
    assert session_before.json()["authenticated"] is False

    bad_login = client.post("/api/auth/login", json={"password": "wrong-password"})
    assert bad_login.status_code == 401

    good_login = client.post("/api/auth/login", json={"password": "correct-admin-password"})
    assert good_login.status_code == 200
    login_data = good_login.json()
    assert login_data["authenticated"] is True
    assert login_data["totp_verified"] is False
    assert COOKIE_NAME in good_login.cookies

    session_mid = client.get("/api/auth/session")
    assert session_mid.status_code == 200
    assert session_mid.json()["authenticated"] is True
    assert session_mid.json()["totp_verified"] is False

    bad_totp = client.post("/api/auth/totp", json={"code": "000000"})
    assert bad_totp.status_code == 401

    totp = pyotp.TOTP("JBSWY3DPEHPK3PXP")
    good_totp = client.post("/api/auth/totp", json={"code": totp.now()})
    assert good_totp.status_code == 200
    totp_data = good_totp.json()
    assert totp_data["authenticated"] is True
    assert totp_data["totp_verified"] is True
    assert totp_data["csrf_token"] is not None

    session_after = client.get("/api/auth/session")
    assert session_after.status_code == 200
    assert session_after.json()["authenticated"] is True
    assert session_after.json()["totp_verified"] is True

    logout = client.post("/api/auth/logout")
    assert logout.status_code == 200
    assert logout.json()["status"] == "logged_out"

    session_end = client.get("/api/auth/session")
    assert session_end.status_code == 200
    assert session_end.json()["authenticated"] is False

