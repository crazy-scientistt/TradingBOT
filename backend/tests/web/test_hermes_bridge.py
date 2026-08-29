from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    monkeypatch.setenv("GOLDGUARD_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("GOLDGUARD_ENVIRONMENT", "test")
    monkeypatch.setenv("GOLDGUARD_MARKET_INGESTION_ENABLED", "false")
    monkeypatch.setenv("GOLDGUARD_GATEWAY_BASE_URL", "")
    monkeypatch.setenv("OPENCODEX_BASE_URL", "")
    monkeypatch.setenv("GOLDGUARD_HERMES_BRIDGE_TOKEN", "bridge-secret")

    from goldguard.web import app as app_module

    with TestClient(app_module.app) as test_client:
        yield test_client


def test_hermes_bridge_rejects_missing_bearer(client: TestClient) -> None:
    res = client.post("/internal/hermes/tools/get_candles", json={"symbol": "PAXGUSDT"})
    assert res.status_code == 401


def test_hermes_bridge_rejects_wrong_bearer(client: TestClient) -> None:
    res = client.post(
        "/internal/hermes/tools/get_candles",
        json={"symbol": "PAXGUSDT"},
        headers={"Authorization": "Bearer wrong"},
    )
    assert res.status_code == 403


def test_hermes_bridge_holdout_stays_sealed(client: TestClient) -> None:
    res = client.post(
        "/internal/hermes/tools/get_evaluation",
        json={"partition": "holdout"},
        headers={"Authorization": "Bearer bridge-secret"},
    )
    assert res.status_code == 403
    assert res.json()["detail"]["code"] == "SEALED_HOLDOUT"


def test_hermes_bridge_get_candles_is_empty_not_synthetic(client: TestClient) -> None:
    res = client.post(
        "/internal/hermes/tools/get_candles",
        json={"symbol": "PAXGUSDT"},
        headers={"Authorization": "Bearer bridge-secret"},
    )
    assert res.status_code == 200
    body = res.json()
    assert body["available"] is True
    assert body["candles"] == []

