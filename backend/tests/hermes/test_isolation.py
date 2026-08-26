import json

import httpx
import pytest
from goldguard.hermes.client import HermesClient
from goldguard.hermes.models import EvaluationPartition, SanitizedResearchPacket
from goldguard.hermes.service import HoldoutEmbargoed, ProposalService


def valid_payload() -> bytes:
    return json.dumps(
        {
            "proposal_id": "proposal-001",
            "parent_version": "safe-default-v1",
            "title": "Require stronger recovery volume",
            "rationale": "Development evidence supports one bounded threshold change.",
            "evidence_refs": ["development-report"],
            "change": {"parameter": "minimum_volume_ratio", "value": "0.95"},
        }
    ).encode()


@pytest.mark.asyncio
async def test_client_uses_bearer_auth_and_sends_only_sanitized_research() -> None:
    observed: dict[str, object] = {}

    async def handler(request: httpx.Request) -> httpx.Response:
        observed["authorization"] = request.headers.get("authorization")
        observed["body"] = json.loads(request.content)
        return httpx.Response(
            200,
            json={"choices": [{"message": {"content": valid_payload().decode()}}]},
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http_client:
        client = HermesClient(
            base_url="http://hermes:8642",
            api_key="dedicated-bridge-secret",
            http_client=http_client,
        )
        result = await client.request_proposal(
            SanitizedResearchPacket(
                market_digest="trend regime with normal volatility",
                recent_trade_summaries=("loss: low volume pullback",),
                evaluation_summaries=("development report ref development-report",),
                evidence_catalog=("development-report",),
            )
        )

    assert observed["authorization"] == "Bearer dedicated-bridge-secret"
    body = observed["body"]
    assert isinstance(body, dict)
    assert body["model"] == "hermes-agent"
    serialized = json.dumps(body).lower()
    assert "binance_api" not in serialized
    assert "broker" not in serialized
    assert result == valid_payload()


def test_holdout_is_embargoed_until_immutable_proposal_is_frozen() -> None:
    service = ProposalService(
        active_parent_version="safe-default-v1",
        evidence_catalog={"development-report"},
    )
    service.submit(valid_payload())

    assert (
        service.evaluation_view("proposal-001", EvaluationPartition.DEVELOPMENT).proposal_id
        == "proposal-001"
    )
    with pytest.raises(HoldoutEmbargoed):
        service.evaluation_view("proposal-001", EvaluationPartition.HOLDOUT)

    frozen = service.freeze_for_holdout("proposal-001")
    assert frozen.frozen is True
    assert service.evaluation_view("proposal-001", EvaluationPartition.HOLDOUT).frozen is True
    assert not hasattr(service, "activate")
