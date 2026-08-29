from __future__ import annotations

import contextlib
import json
from collections.abc import Iterator
from pathlib import Path

import pyotp
import pytest
from fastapi.testclient import TestClient
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
        yield test_client


def valid_profile_payload() -> dict:
    return {
        "execution_mode": "paper",
        "strategy_mode": "autonomous",
        "autonomous_profile": "micro_trade",
        "spot_enabled": True,
        "futures_enabled": True,
        "spot_pairs": ["PAXGUSDT"],
        "futures_pairs": ["BTCUSDT", "ETHUSDT"],
        "risk": {
            "max_capital_per_trade_rate": "0.005",
            "max_futures_leverage": 5,
            "max_total_exposure_rate": "0.20",
            "rolling_24h_loss_limit_rate": "0.03",
        },
        "notifications": {
            "telegram_enabled": False,
            "notify_on_entry": True,
            "notify_on_exit": True,
            "notify_on_error": True,
        },
    }


def login_full_auth(client: TestClient) -> dict[str, str]:
    login_res = client.post("/api/auth/login", json={"password": "correct-admin-password"})
    assert login_res.status_code == 200
    totp = pyotp.TOTP("JBSWY3DPEHPK3PXP")
    totp_res = client.post("/api/auth/totp", json={"code": totp.now()})
    assert totp_res.status_code == 200
    csrf_token = totp_res.json()["csrf_token"]
    return {"X-CSRF-Token": csrf_token}


def test_profile_preview_endpoint(client: TestClient) -> None:
    response = client.post("/api/settings/profile/preview", json=valid_profile_payload())
    assert response.status_code == 200
    body = response.json()
    assert body["equivalents"]["max_capital_per_trade_usdt"] == "50.00"
    assert body["equivalents"]["max_total_exposure_usdt"] == "2000.00"
    assert body["equivalents"]["rolling_24h_loss_limit_usdt"] == "300.00"
    assert body["blockers"] == []


def test_profile_get_endpoint_returns_usdt_equivalents(client: TestClient) -> None:
    response = client.get("/api/settings/profile")
    assert response.status_code == 200
    body = response.json()
    assert body["equivalents"]["max_capital_per_trade_usdt"] == "50.00"
    assert "api_key" not in json.dumps(body).lower()


def test_profile_mutation_requires_auth_and_csrf(client: TestClient) -> None:
    # 1. Unauthenticated mutation
    unauth = client.post("/api/settings/profile", json=valid_profile_payload())
    assert unauth.status_code == 401

    # 2. Login password only (no CSRF or TOTP)
    client.post("/api/auth/login", json={"password": "correct-admin-password"})
    no_csrf = client.post("/api/settings/profile", json=valid_profile_payload())
    assert no_csrf.status_code == 403

    # 3. Full login with TOTP and CSRF
    headers = login_full_auth(client)
    success = client.post("/api/settings/profile", json=valid_profile_payload(), headers=headers)
    assert success.status_code == 200
    body = success.json()
    assert body["hash"] is not None
    assert body["created_by"] == "admin"
    assert body["equivalents"]["max_capital_per_trade_usdt"] == "50.00"

