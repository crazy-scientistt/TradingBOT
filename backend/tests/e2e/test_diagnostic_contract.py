from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from goldguard.operations.stack import REQUIRED_CHECKS


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


def test_diagnostics_endpoint_lists_every_required_check(client: TestClient) -> None:
    body = client.get("/api/diagnostics").json()
    assert body["availability"] == "available"
    data = body["data"]
    names = {item["name"] for item in data["checks"]}
    assert set(REQUIRED_CHECKS) <= names
    assert data["live_armed"] is False
    assert data["real_orders_placed"] == 0
    assert "OPENCODEX_UNCONFIGURED" in data["blockers"]
