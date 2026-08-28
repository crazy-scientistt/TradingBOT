from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client(tmp_path, monkeypatch) -> Iterator[TestClient]:
    monkeypatch.setenv("GOLDGUARD_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("GOLDGUARD_ENVIRONMENT", "test")
    monkeypatch.setenv("GOLDGUARD_MARKET_INGESTION_ENABLED", "false")
    monkeypatch.setenv("GOLDGUARD_GATEWAY_BASE_URL", "")
    monkeypatch.setenv("OPENCODEX_BASE_URL", "")
    monkeypatch.setenv("GOLDGUARD_PAPER_STARTING_BALANCE", "100")

    from goldguard.web import app as app_module

    with TestClient(app_module.app) as test_client:
        yield test_client


def test_settings_save_in_the_app_without_restart(client: TestClient) -> None:
    before = client.get("/api/settings")
    assert before.status_code == 200
    payload = before.json()["data"]
    assert payload["mutable"] is True
    assert payload["paper_starting_balance"] == "100"

    saved = client.post(
        "/api/settings",
        json={"paper_starting_balance": "25000", "paper_risk_per_trade": "0.005"},
    )
    assert saved.status_code == 200, saved.text
    data = saved.json()["data"]
    assert data["paper_starting_balance"] == "25000"
    assert data["paper_risk_per_trade"] == "0.005"

    again = client.get("/api/settings").json()["data"]
    assert again["paper_starting_balance"] == "25000"


def test_settings_reject_risk_above_hard_ceiling(client: TestClient) -> None:
    response = client.post("/api/settings", json={"paper_risk_per_trade": "0.05"})
    assert response.status_code == 422
