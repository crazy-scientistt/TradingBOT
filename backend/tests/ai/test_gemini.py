import json

import httpx
import pytest
from goldguard.ai.gemini import DecisionRequest, GeminiDecisionClient
from goldguard.domain.enums import AiDecision, CandidateAction


def response_payload(
    *,
    decision: str = "APPROVE_ENTRY",
    confidence: int = 72,
    reason_codes: list[str] | None = None,
) -> dict[str, object]:
    body = {
        "decision": decision,
        "confidence": confidence,
        "reason_codes": reason_codes or ["TREND_ALIGNED"],
        "rationale": "Trend, liquidity, and cited context agree.",
        "memory_refs": [],
    }
    return {"candidates": [{"content": {"parts": [{"text": json.dumps(body)}]}}]}


def request() -> DecisionRequest:
    return DecisionRequest(
        candidate=CandidateAction.ENTRY_CANDIDATE,
        strategy_version="strategy-v1",
        features={"rsi14": 50.0, "spread_rate": 0.0004},
        context={"drivers": ["rates"], "citations": 2},
        memory_summaries=(),
    )


@pytest.mark.asyncio
async def test_valid_schema_approves_compatible_high_confidence_entry() -> None:
    seen: list[httpx.Request] = []

    def handler(raw_request: httpx.Request) -> httpx.Response:
        seen.append(raw_request)
        return httpx.Response(200, json=response_payload())

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http_client:
        client = GeminiDecisionClient(
            api_key="synthetic-key",
            model="gemini-2.5-flash",
            http_client=http_client,
            minimum_confidence=65,
        )
        result = await client.decide(request())

    assert result.decision is AiDecision.APPROVE_ENTRY
    assert result.confidence == 72
    assert result.prompt_hash
    payload = json.loads(seen[0].content)
    assert payload["generationConfig"]["responseMimeType"] == "application/json"
    assert "tools" not in payload
    assert "synthetic-key" not in seen[0].content.decode()
    assert seen[0].headers["x-goog-api-key"] == "synthetic-key"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("payload", "expected_reason"),
    [
        (response_payload(confidence=64), "LOW_CONFIDENCE"),
        (response_payload(decision="EXIT"), "INCOMPATIBLE_AI_DECISION"),
        (response_payload(reason_codes=["UNKNOWN_CODE"]), "INVALID_AI_RESPONSE"),
        ({"candidates": []}, "INVALID_AI_RESPONSE"),
    ],
)
async def test_invalid_or_low_confidence_output_fails_closed(
    payload: dict[str, object],
    expected_reason: str,
) -> None:
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(lambda _: httpx.Response(200, json=payload))
    ) as http_client:
        client = GeminiDecisionClient(
            api_key="synthetic-key",
            model="gemini-2.5-flash",
            http_client=http_client,
            minimum_confidence=65,
        )
        result = await client.decide(request())

    assert result.decision is AiDecision.REJECT_ENTRY
    assert result.reason_codes == (expected_reason,)


@pytest.mark.asyncio
async def test_timeout_fails_closed_without_exposing_error_details() -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("upstream timeout with synthetic-key")

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http_client:
        result = await GeminiDecisionClient(
            api_key="synthetic-key",
            model="gemini-2.5-flash",
            http_client=http_client,
            minimum_confidence=65,
        ).decide(request())

    assert result.decision is AiDecision.REJECT_ENTRY
    assert result.reason_codes == ("MODEL_UNAVAILABLE",)
    assert "synthetic-key" not in result.rationale
