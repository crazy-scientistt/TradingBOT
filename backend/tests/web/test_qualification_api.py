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


def test_qualification_report_route(client: TestClient) -> None:
    res = client.get("/api/qualification/report")
    assert res.status_code == 200
    body = res.json()
    assert "ready_for_live_canary" in body
    assert "gates" in body
    assert len(body["gates"]) >= 10
    assert body["ready_for_live_canary"] is False


def test_qualification_latest_is_fail_closed(client: TestClient) -> None:
    res = client.get("/api/qualification/latest")
    assert res.status_code == 200
    body = res.json()
    assert body["ready_for_live_canary"] is False
    assert any("NOT_READY" in item for item in body["blockers"])

