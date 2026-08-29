from __future__ import annotations

from collections.abc import Iterator
from decimal import Decimal
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from goldguard.domain.enums import (
    ExecutionMode,
    MarginMode,
    PositionSide,
    ProductKind,
)
from goldguard.execution.models import PositionRecord
from goldguard.storage.execution_repository import ExecutionRepository


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


def test_empty_orders_are_truthful_empty_not_seeded(client: TestClient) -> None:
    body = client.get("/api/orders").json()
    assert body["availability"] == "available"
    assert body["data"] == []


def test_empty_holdings_and_pnl_are_available_empty_not_seeded(client: TestClient) -> None:
    holdings = client.get("/api/holdings").json()
    assert holdings["availability"] == "available"
    assert holdings["data"] == []
    pnl = client.get("/api/pnl").json()
    assert pnl["availability"] == "available"
    assert pnl["data"] == []
    diagnostics = client.get("/api/diagnostics").json()
    assert diagnostics["availability"] == "available"
    assert "blockers" in diagnostics["data"]


def test_position_net_pnl_reconciles_costs(client: TestClient, tmp_path: Path) -> None:
    from goldguard.web import app as app_module

    assert app_module._db is not None
    repo = ExecutionRepository(app_module._db)
    pos = PositionRecord(
        position_id="pos-test",
        mode=ExecutionMode.PAPER,
        product=ProductKind.FUTURES,
        symbol="BTCUSDT",
        side=PositionSide.LONG,
        quantity=Decimal("0.01"),
        entry_price=Decimal("50000.00"),
        current_price=Decimal("55000.00"),
        margin_mode=MarginMode.ISOLATED,
        leverage=5,
        isolated_margin=Decimal("100.00"),
        unrealized_pnl=Decimal("50.00"),
        opened_at="2026-08-29T12:00:00+00:00",
        updated_at="2026-08-29T12:00:05+00:00",
    )
    repo.save_position(pos)

    res = client.get("/api/positions").json()
    assert res["availability"] == "available"
    positions = res["data"]
    assert len(positions) == 1
    p = positions[0]
    assert p["symbol"] == "BTCUSDT"
    assert Decimal(p["gross_pnl_usdt"]) == Decimal("50.00")
    expected_net = (
        Decimal(p["gross_pnl_usdt"])
        - Decimal(p["fees_usdt"])
        - Decimal(p["funding_usdt"])
        - Decimal(p["slippage_usdt"])
    )
    assert Decimal(p["net_pnl_usdt"]) == expected_net

