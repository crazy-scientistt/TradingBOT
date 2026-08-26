import json
from pathlib import Path

import httpx
import pytest
from goldguard.ai.decision import DecisionVetoEngine
from goldguard.ai.gemini import DecisionRequest
from goldguard.domain.enums import AiDecision, CandidateAction
from goldguard.providers.client import GatewayClient
from goldguard.providers.service import RouteService
from goldguard.storage.database import Database
from goldguard.storage.repositories import ProviderRepository


@pytest.fixture
def database(tmp_path: Path) -> Database:
    db = Database(tmp_path / "goldguard.db")
    db.migrate()
    return db


def request() -> DecisionRequest:
    return DecisionRequest(
        candidate=CandidateAction.ENTRY_CANDIDATE,
        strategy_version="trend-pullback-v1",
        features={"rsi14": 52.0, "spread_rate": 0.0004},
        context={"citations": 2, "conflict_level": "LOW"},
        memory_summaries=(),
    )


@pytest.mark.asyncio
async def test_decision_veto_engine_approves_valid_gemini_response(database: Database) -> None:
    repo = ProviderRepository(database)
    repo.upsert_provider(
        name="opencodex",
        kind="opencodex",
        base_url="http://localhost:10100",
        key_fingerprint="sha256:test",
        status="active",
    )
    route_service = RouteService(repo)
    route_service.set_route(
        role="decision",
        provider="opencodex",
        model="google-antigravity/gemini-3.7-flash",
    )

    resp_body = {
        "decision": "APPROVE_ENTRY",
        "confidence": 88,
        "reason_codes": ["TREND_ALIGNED", "LIQUIDITY_GOOD"],
        "rationale": "High confidence trend alignment.",
        "memory_refs": [],
    }

    async def mock_handler(req: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "id": "chat-1",
                "model": "google-antigravity/gemini-3.7-flash",
                "choices": [
                    {
                        "index": 0,
                        "message": {"role": "assistant", "content": json.dumps(resp_body)},
                    }
                ],
            },
        )

    transport = httpx.MockTransport(mock_handler)
    async with httpx.AsyncClient(transport=transport) as http_client:
        gateway = GatewayClient(base_url="http://localhost:10100", http_client=http_client)
        engine = DecisionVetoEngine(
            route_service=route_service,
            gateway_client=gateway,
            minimum_confidence=70,
        )
        assessment = await engine.decide(request())

    assert assessment.decision is AiDecision.APPROVE_ENTRY
    assert assessment.confidence == 88
    assert assessment.model == "google-antigravity/gemini-3.7-flash"
    assert assessment.reason_codes == ("TREND_ALIGNED", "LIQUIDITY_GOOD")
    assert assessment.prompt_hash


@pytest.mark.asyncio
async def test_decision_veto_engine_rejects_low_conf_and_bad_schema(
    database: Database,
) -> None:
    repo = ProviderRepository(database)
    repo.upsert_provider(
        name="opencodex",
        kind="opencodex",
        base_url="http://localhost:10100",
        key_fingerprint="sha256:test",
        status="active",
    )
    route_service = RouteService(repo)
    route_service.set_route(
        role="decision",
        provider="opencodex",
        model="google-antigravity/gemini-3.7-flash",
    )

    # 1. Low confidence
    low_conf_body = {
        "decision": "APPROVE_ENTRY",
        "confidence": 65,  # Below 70%
        "reason_codes": ["TREND_ALIGNED"],
        "rationale": "Low confidence setup.",
        "memory_refs": [],
    }

    async def mock_low_conf(req: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "id": "chat-2",
                "model": "google-antigravity/gemini-3.7-flash",
                "choices": [
                    {
                        "index": 0,
                        "message": {"role": "assistant", "content": json.dumps(low_conf_body)},
                    }
                ],
            },
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(mock_low_conf)) as http_client:
        gateway = GatewayClient(base_url="http://localhost:10100", http_client=http_client)
        engine = DecisionVetoEngine(
            route_service=route_service,
            gateway_client=gateway,
            minimum_confidence=70,
        )
        assessment = await engine.decide(request())
    assert assessment.decision is AiDecision.REJECT_ENTRY
    assert assessment.reason_codes == ("LOW_CONFIDENCE",)

    # 2. Invalid schema (missing required fields)
    async def mock_bad_schema(req: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "id": "chat-3",
                "model": "google-antigravity/gemini-3.7-flash",
                "choices": [
                    {
                        "index": 0,
                        "message": {"role": "assistant", "content": '{"foo": "bar"}'},
                    }
                ],
            },
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(mock_bad_schema)) as http_client:
        gateway = GatewayClient(base_url="http://localhost:10100", http_client=http_client)
        engine = DecisionVetoEngine(
            route_service=route_service,
            gateway_client=gateway,
            minimum_confidence=70,
        )
        assessment = await engine.decide(request())
    assert assessment.decision is AiDecision.REJECT_ENTRY
    assert assessment.reason_codes == ("INVALID_AI_RESPONSE",)


@pytest.mark.asyncio
async def test_decision_veto_engine_gateway_timeout_fails_closed(database: Database) -> None:
    repo = ProviderRepository(database)
    route_service = RouteService(repo)

    async def mock_timeout(req: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("gateway timeout")

    async with httpx.AsyncClient(transport=httpx.MockTransport(mock_timeout)) as http_client:
        gateway = GatewayClient(base_url="http://localhost:10100", http_client=http_client)
        engine = DecisionVetoEngine(
            route_service=route_service,
            gateway_client=gateway,
            minimum_confidence=70,
        )
        assessment = await engine.decide(request())

    assert assessment.decision is AiDecision.REJECT_ENTRY
    assert assessment.reason_codes == ("INVALID_AI_RESPONSE",)
