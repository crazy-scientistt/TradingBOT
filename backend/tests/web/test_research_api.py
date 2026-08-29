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

    from goldguard.web import app as app_module

    with TestClient(app_module.app) as test_client:
        yield test_client


def test_unavailable_research_returns_truthful_envelope(client: TestClient) -> None:
    res = client.get("/api/research/evidence?product=spot&symbol=PAXGUSDT")
    assert res.status_code == 200
    data = res.json()
    assert "availability" in data
    assert "data" in data


def test_research_health_route(client: TestClient) -> None:
    res = client.get("/api/research/health")
    assert res.status_code == 200
    data = res.json()
    assert "status" in data
    assert "adapters" in data

