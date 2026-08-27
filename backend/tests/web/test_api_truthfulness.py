"""Truthfulness contract for the HTTP layer.

Every assertion here exists because the endpoint used to invent a value: synthetic
candles, a representative flat position, a hard-coded equity curve, static macro
headlines, random provider latencies, or a profitable backtest on failure.
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client(tmp_path, monkeypatch) -> Iterator[TestClient]:
    monkeypatch.setenv("GOLDGUARD_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("GOLDGUARD_ENVIRONMENT", "test")
    monkeypatch.setenv("GOLDGUARD_MARKET_INGESTION_ENABLED", "false")
    # Empty, not deleted: the repo ships a .env that pydantic-settings would otherwise
    # read, which would make these results depend on the developer's local file.
    monkeypatch.setenv("GOLDGUARD_GATEWAY_BASE_URL", "")
    monkeypatch.setenv("OPENCODEX_BASE_URL", "")

    from goldguard.web import app as app_module

    with TestClient(app_module.app) as test_client:
        yield test_client


def _envelope(response) -> dict:
    assert response.status_code == 200, response.text
    body = response.json()
    for key in ("availability", "source", "observed_at", "stale", "data"):
        assert key in body, f"missing envelope key {key!r} in {sorted(body)}"
    assert body["availability"] in {"available", "degraded", "unavailable"}
    return body


# --- no fabricated market data -------------------------------------------------


def test_candles_are_unavailable_instead_of_synthetic(client: TestClient) -> None:
    body = _envelope(client.get("/api/market/candles"))
    assert body["availability"] == "unavailable"
    assert body["data"] == []
    # A second call must not "helpfully" generate a random walk to fill the gap.
    assert _envelope(client.get("/api/market/candles"))["data"] == []


def test_quote_is_unavailable_before_ingestion(client: TestClient) -> None:
    body = _envelope(client.get("/api/market/quote"))
    assert body["availability"] == "unavailable"
    assert body["data"] is None


# --- no fabricated account state ----------------------------------------------


def test_flat_account_returns_no_position_object(client: TestClient) -> None:
    body = _envelope(client.get("/api/position"))
    assert body["data"]["hasPosition"] is False
    assert body["data"]["position"] is None


def test_equity_curve_is_empty_without_snapshots(client: TestClient) -> None:
    body = _envelope(client.get("/api/equity"))
    assert body["data"] == []
    assert body["availability"] == "unavailable"


def test_kpi_reports_unknown_drawdown_without_history(client: TestClient) -> None:
    body = _envelope(client.get("/api/kpi"))
    data = body["data"]
    assert data["maxDrawdown"] is None
    assert data["liveSpread"] is None
    assert data["equity"] == 100.0


def test_bot_state_daily_loss_is_measured_not_assumed(client: TestClient) -> None:
    body = _envelope(client.get("/api/bot/state"))
    assert body["data"]["daily_loss_percent"] == 0.0


# --- no fabricated context or memory -----------------------------------------


def test_context_has_no_static_headlines(client: TestClient) -> None:
    body = _envelope(client.get("/api/context"))
    assert body["data"] == []
    assert body["availability"] == "unavailable"


def test_reflections_are_not_seeded_at_boot(client: TestClient) -> None:
    body = _envelope(client.get("/api/reflections"))
    assert body["data"] == []


def test_reflection_fields_use_frontend_names(client: TestClient, tmp_path) -> None:
    from decimal import Decimal

    from goldguard.web import app as app_module

    assert app_module._reflection_repo is not None
    app_module._reflection_repo.record_reflection(
        reflection_id="ref-1",
        trade_id="t-1",
        namespace="forward",
        lesson_code="TP_CLEAN",
        lesson="Target reached before invalidation.",
        regime_tags=["trend"],
        net_pnl=Decimal("2.40"),
        fee_drag=Decimal("0.22"),
        mae=Decimal("1.20"),
        mfe=Decimal("4.50"),
        exit_reason="TAKE_PROFIT",
        payload={"symbol": "PAXGUSDT"},
    )
    row = _envelope(client.get("/api/reflections"))["data"][0]
    assert row["net_pnl"] == "2.40"
    assert row["regime_tags"] == ["trend"]
    assert "net_pnl_text" not in row
    assert "regime_tags_json" not in row


# --- no fabricated provider health -------------------------------------------


def test_providers_report_unprobed_rather_than_a_latency(client: TestClient) -> None:
    body = _envelope(client.get("/api/providers"))
    assert body["data"], "seeded routes require provider rows"
    for provider in body["data"]:
        assert provider["latency_ms"] is None
        assert provider["probe_status"] == "unprobed"
        assert "mock" not in provider["key_fingerprint"]


def test_probe_without_a_configured_gateway_is_unavailable(client: TestClient) -> None:
    body = _envelope(client.post("/api/providers/probe"))
    assert body["availability"] == "unavailable"
    for provider in body["data"]:
        assert provider["latency_ms"] is None
        assert provider["probe_status"] == "unconfigured"


# --- no fabricated performance ------------------------------------------------


def test_backtest_refuses_to_run_without_a_verified_dataset(client: TestClient) -> None:
    genome = _envelope(client.get("/api/genomes"))["data"][0]
    response = client.post("/api/backtest/run", json={"genome": genome})
    assert response.status_code == 409
    assert "24.5" not in response.text
    assert "1.85" not in response.text


def test_genome_list_carries_the_full_specification(client: TestClient) -> None:
    genomes = _envelope(client.get("/api/genomes"))["data"]
    assert genomes
    for field in ("title", "evidence_refs", "regime", "guard", "entry", "exit", "genome_hash"):
        assert field in genomes[0], f"{field} missing — the Studio editor dereferences it"


# --- snapshot, events, preflight ---------------------------------------------


def test_dashboard_snapshot_covers_every_polled_section(client: TestClient) -> None:
    response = client.get("/api/dashboard")
    assert response.status_code == 200, response.text
    body = response.json()
    for section in (
        "health",
        "status",
        "kpi",
        "quote",
        "candles",
        "position",
        "equity",
        "context",
        "genomes",
        "providers",
        "routes",
        "quota",
        "reflections",
        "botState",
        "agentEvents",
        "preflight",
    ):
        assert section in body, f"{section} missing from the dashboard snapshot"


def test_agent_events_are_bounded_to_thirty(client: TestClient) -> None:
    body = _envelope(client.get("/api/agent/events?limit=500"))
    assert len(body["data"]) <= 30


def test_agent_event_stream_opens_with_a_snapshot_frame(client: TestClient) -> None:
    from goldguard.observability.events import AgentEvent
    from goldguard.web import app as app_module

    published = AgentEvent.create(
        action="HOLD",
        reason="Checklist Held",
        reason_codes=("CHECKLIST_HELD",),
        payload={"outcome_action": "CHECKLIST_HELD"},
    )

    async def read_two_frames() -> list[str]:
        response = await app_module.agent_event_stream()
        assert response.media_type == "text/event-stream"
        # TestClient buffers whole response bodies, so an endless SSE body has to be
        # consumed from the generator directly.
        frames = app_module._agent_event_frames()
        try:
            first = await anext(frames)
            runtime = app_module._trading_runtime
            assert runtime is not None
            runtime._event_bus.publish(published)
            return [first, await anext(frames)]
        finally:
            await frames.aclose()

    first, second = asyncio.run(read_two_frames())

    lines = first.strip().split("\n")
    assert lines[0] == "event: snapshot"
    payload = json.loads(lines[1][6:])
    assert isinstance(payload["events"], list)

    assert second.startswith("event: agent_event")
    live = json.loads(second.strip().split("\n")[1][6:])
    assert live["event_id"] == published.event_id
    assert live["reason_codes"] == ["CHECKLIST_HELD"]


def test_preflight_blocks_start_and_explains_why(client: TestClient) -> None:
    body = client.get("/api/preflight").json()
    assert body["ready"] is False
    failed = {check["id"] for check in body["checks"] if check["status"] == "fail"}
    assert "market_data" in failed
    for check in body["checks"]:
        assert check["detail"], "a beginner needs a readable reason for every gate"

    response = client.post("/api/bot/start")
    assert response.status_code == 409
    assert response.json()["detail"]


def test_emergency_stop_cannot_be_cleared_by_start(client: TestClient) -> None:
    assert client.post("/api/bot/stop").status_code == 200
    assert _envelope(client.get("/api/bot/status"))["data"]["halted"] is True
    response = client.post("/api/bot/start")
    assert response.status_code == 409
    assert "halted" in response.json()["detail"].lower()
