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


def test_live_is_always_200(client: TestClient) -> None:
    res = client.get("/api/health/live")
    assert res.status_code == 200
    assert res.json() == {"status": "alive"}


def test_ready_is_200_when_database_initialized(client: TestClient) -> None:
    res = client.get("/api/health/ready")
    assert res.status_code == 200
    assert res.json()["status"] == "ready"


def test_existing_health_probe_still_works(client: TestClient) -> None:
    res = client.get("/api/health")
    assert res.status_code == 200
    assert "status" in res.json()


def test_ready_fails_closed_without_database(monkeypatch: pytest.MonkeyPatch) -> None:
    from fastapi.responses import JSONResponse
    from goldguard.web import app as app_module
    from goldguard.web.routes import health as health_routes

    monkeypatch.setattr(app_module, "_db", None)
    res = health_routes.ready()
    assert isinstance(res, JSONResponse)
    assert res.status_code == 503
    assert res.body and b"DATABASE_UNINITIALIZED" in res.body
