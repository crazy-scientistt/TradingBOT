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


def test_unknown_chart_interval_is_rejected(client: TestClient) -> None:
    response = client.get("/api/market/candles?interval=2m")
    assert response.status_code == 400


def test_market_stream_route_exists() -> None:
    from goldguard.web.app import app

    paths = {getattr(route, "path", None) for route in app.routes}
    assert "/api/market/stream" in paths
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
    assert data["equity"] == 10000.0


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


def test_opencodex_catalog_is_unavailable_without_a_gateway(client: TestClient) -> None:
    body = _envelope(client.get("/api/providers/catalog"))
    assert body["availability"] == "unavailable"
    assert body["data"] == []
    assert "OpenCodex" in (body["detail"] or "")


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
        "catalog",
        "routes",
        "quota",
        "reflections",
        "botState",
        "agentEvents",
        "preflight",
        "promotionCanary",
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


# --- autonomy is a durable kill switch ----------------------------------------


def test_revoked_autonomy_survives_a_restart(tmp_path, monkeypatch) -> None:
    """A revocation is a switch an operator threw. It must not come back on at boot."""
    monkeypatch.setenv("GOLDGUARD_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("GOLDGUARD_ENVIRONMENT", "test")
    monkeypatch.setenv("GOLDGUARD_MARKET_INGESTION_ENABLED", "false")
    monkeypatch.setenv("GOLDGUARD_GATEWAY_BASE_URL", "")
    monkeypatch.setenv("OPENCODEX_BASE_URL", "")

    import importlib

    from goldguard.web import app as app_module

    first = importlib.reload(app_module)
    with TestClient(first.app) as client:
        assert _envelope(client.get("/api/status"))["data"]["full_autonomy"] is True
        revoked = client.post(
            "/api/bot/revoke-autonomy",
            json={"reason": "operator paused research during a drawdown"},
        )
        assert revoked.status_code == 200, revoked.text
        assert revoked.json()["full_autonomy"] is False
        assert client.post("/api/hermes/step").status_code == 409

    restarted = importlib.reload(app_module)
    with TestClient(restarted.app) as client:
        state = _envelope(client.get("/api/bot/state"))["data"]
        assert state["full_autonomy"] is False
        assert state["autonomy_revoked_reason"] == "operator paused research during a drawdown"
        assert client.post("/api/hermes/step").status_code == 409

        restored = client.post("/api/bot/restore-autonomy")
        assert restored.status_code == 200, restored.text
        assert restored.json()["full_autonomy"] is True
        assert _envelope(client.get("/api/status"))["data"]["full_autonomy"] is True


def test_revoking_autonomy_requires_a_reason(client: TestClient) -> None:
    """An unexplained kill switch is an unauditable one."""
    response = client.post("/api/bot/revoke-autonomy", json={"reason": "   "})
    assert response.status_code == 422


# --- autonomous promotion wiring ----------------------------------------------


def test_lifespan_constructs_hermes_loop_and_promotion_controller(client: TestClient) -> None:
    from goldguard.web import app as app_module

    assert app_module._hermes_loop is not None
    assert app_module._promotion_controller is not None
    assert app_module._hermes_loop.promotion_controller is app_module._promotion_controller


def test_hermes_step_delegates_to_the_constructed_loop(client: TestClient, monkeypatch) -> None:
    from decimal import Decimal

    from goldguard.hermes.loop import LoopIterationResult
    from goldguard.services.ingestion import MarketSnapshot
    from goldguard.services.promotion_controller import EvidenceDataset, ShadowEvidence
    from goldguard.web import app as app_module

    calls: list[object] = []

    class FakeLoop:
        promotion_controller = app_module._promotion_controller

        async def step(self, **kwargs):  # type: ignore[no-untyped-def]
            calls.append(kwargs)
            return LoopIterationResult(
                iteration_id="hermes-test",
                status="promoted_candidate",
                candidate_genome_id="candidate-test",
                quota_used=(1, 0),
            )

    monkeypatch.setattr(
        app_module,
        "_market",
        lambda: MarketSnapshot(
            availability="available",
            source="test",
            observed_at=None,
            stale=False,
            detail=None,
            verified=True,
            candles_15m=(),
            candles_1h=(),
            latest_quote=None,
            filters=None,
        ),
    )
    monkeypatch.setattr(app_module, "_hermes_loop", FakeLoop())
    monkeypatch.setattr(
        app_module,
        "_hermes_dataset",
        lambda market: EvidenceDataset(
            dataset_id="test",
            verified=True,
            candles_15m=tuple(market.candles_15m),
            shadow=ShadowEvidence(
                days=0,
                net_pnl=Decimal("0"),
                trades=0,
                slippage_acceptable=True,
            ),
        ),
    )
    response = client.post("/api/hermes/step")

    assert response.status_code == 200, response.text
    assert calls, "the route must invoke HermesResearchLoop.step"
    assert response.json()["status"] == "promoted_candidate"


def test_bot_state_exposes_canary_and_drives_controller_from_ledger(
    client: TestClient, monkeypatch
) -> None:
    from goldguard.services.promotion_controller import CanaryEvent
    from goldguard.strategy.genome import trend_pullback_v1
    from goldguard.web import app as app_module

    assert app_module._promotion_controller is not None
    observed: list[CanaryEvent] = []

    def observe(event: CanaryEvent):
        observed.append(event)
        return None

    monkeypatch.setattr(app_module._promotion_controller, "on_canary_event", observe)
    assert app_module._promotion_repo is not None
    assert app_module._genome_repo is not None
    baseline = app_module._genome_repo.get_active_genome() or trend_pullback_v1()
    candidate = baseline.model_copy(
        update={"genome_id": "canary-test", "parent_id": baseline.genome_id}
    )
    app_module._genome_repo.save_genome(candidate, origin="hermes", status="active")
    app_module._promotion_repo.open_canary(
        genome_id=candidate.genome_id,
        promotion_id="promotion-test",
        baseline_genome_id=baseline.genome_id,
        baseline_hash="baseline-hash",
    )
    state = _envelope(client.get("/api/bot/state"))["data"]

    assert "canary" in state
    assert state["canary"]["status"] == "canary"
    assert observed and observed[0].genome_id == candidate.genome_id
    assert observed[0].drawdown == 0
    assert observed[0].error_count == 0
    assert observed[0].trades == 0


def test_legacy_genome_promote_endpoint_cannot_bypass_controller(client: TestClient) -> None:
    response = client.post("/api/genomes/promote", json={"genome_id": "anything"})
    assert response.status_code == 409
    assert "PromotionController" in response.text


def test_canary_endpoint_is_enveloped_and_truthful_when_empty(client: TestClient) -> None:
    body = _envelope(client.get("/api/promotion/canary"))
    assert body["data"]["status"] == "none"


def test_durable_runtime_error_triggers_canary_rollback_via_endpoint(client: TestClient) -> None:
    from goldguard.web import app as app_module

    assert app_module._promotion_repo is not None
    assert app_module._genome_repo is not None
    assert app_module._ledger_repo is not None
    baseline = app_module._genome_repo.get_active_genome()
    assert baseline is not None
    candidate = baseline.model_copy(
        update={"genome_id": "runtime-error-canary", "parent_id": baseline.genome_id}
    )
    app_module._genome_repo.save_genome(candidate, origin="hermes", status="active")
    app_module._promotion_repo.open_canary(
        genome_id=candidate.genome_id,
        promotion_id="promotion-error-test",
        baseline_genome_id=baseline.genome_id,
        baseline_hash="baseline-hash",
    )
    for index in range(3):
        app_module._ledger_repo.record_runtime_error(f"exchange tick failed {index}")

    body = _envelope(client.get("/api/promotion/canary"))["data"]
    assert body["status"] == "rolled_back"
    assert "CANARY_ERROR_BUDGET_EXCEEDED" in body["rollback_reason"]
