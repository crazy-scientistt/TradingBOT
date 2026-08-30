import json

import httpx
import pytest
from goldguard.hermes.client import HermesClient
from goldguard.hermes.generator import (
    ProposalValidationError,
    StrategyProposalGenerator,
)
from goldguard.strategy.genome import genome_hash, trend_pullback_v1


@pytest.mark.asyncio
async def test_proposal_generator_creates_valid_bounded_genome() -> None:
    parent = trend_pullback_v1()

    proposal_json = {
        "hypothesis": "Increasing volume ratio threshold reduces low-liquidity false breakouts.",
        "evidence_refs": ["ref-101", "loss-cluster-chop"],
        "parameter_changes": {
            "minimum_volume_ratio": "1.05",
        },
    }

    async def mock_handler(req: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "id": "chat-hermes-1",
                "model": "google-antigravity/gemini-3.7-flash",
                "choices": [
                    {
                        "index": 0,
                        "message": {"role": "assistant", "content": json.dumps(proposal_json)},
                    }
                ],
            },
        )

    transport = httpx.MockTransport(mock_handler)
    async with httpx.AsyncClient(transport=transport) as http_client:
        hermes = HermesClient(
            base_url="http://hermes.test",
            api_key="test-key",
            http_client=http_client,
        )
        generator = StrategyProposalGenerator(hermes_client=hermes)
        proposal_genome = await generator.propose(
            parent_genome=parent,
            reflections=[{"lesson_code": "CHOP_WHIPSAW", "lesson": "False breakout in low volume"}],
            market_summary="Chop regime with declining volume",
        )

    assert proposal_genome.parent_id == parent.genome_id
    assert proposal_genome.hypothesis == proposal_json["hypothesis"]
    assert "ref-101" in proposal_genome.evidence_refs
    assert genome_hash(proposal_genome) != genome_hash(parent)


@pytest.mark.asyncio
async def test_proposal_generator_rejects_out_of_bounds_parameter() -> None:
    parent = trend_pullback_v1()

    # minimum_volume_ratio max bound is 5.0, here we simulate LLM attempting 8.0
    bad_proposal_json = {
        "hypothesis": "Extreme volume requirement",
        "evidence_refs": ["ref-1"],
        "parameter_changes": {
            "minimum_volume_ratio": "8.0",  # Out of bounds!
        },
    }

    async def mock_handler(req: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "id": "chat-hermes-2",
                "model": "google-antigravity/gemini-3.7-flash",
                "choices": [
                    {
                        "index": 0,
                        "message": {"role": "assistant", "content": json.dumps(bad_proposal_json)},
                    }
                ],
            },
        )

    transport = httpx.MockTransport(mock_handler)
    async with httpx.AsyncClient(transport=transport) as http_client:
        hermes = HermesClient(
            base_url="http://hermes.test",
            api_key="test-key",
            http_client=http_client,
        )
        generator = StrategyProposalGenerator(hermes_client=hermes)
        with pytest.raises(ProposalValidationError, match="outside safe parameter bounds"):
            await generator.propose(
                parent_genome=parent,
                reflections=[],
                market_summary="Test",
            )


@pytest.mark.asyncio
async def test_proposal_generator_rejects_more_than_two_mutations() -> None:
    parent = trend_pullback_v1()

    too_many_changes = {
        "hypothesis": "Over-mutating multiple parameters",
        "evidence_refs": ["ref-1"],
        "parameter_changes": {
            "rsi_entry_recovery": "50",
            "minimum_volume_ratio": "1.1",
            "atr_stop_multiple": "1.8",  # 3rd change exceeds limit of 2!
        },
    }

    async def mock_handler(req: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "id": "chat-hermes-3",
                "model": "google-antigravity/gemini-3.7-flash",
                "choices": [
                    {
                        "index": 0,
                        "message": {"role": "assistant", "content": json.dumps(too_many_changes)},
                    }
                ],
            },
        )

    transport = httpx.MockTransport(mock_handler)
    async with httpx.AsyncClient(transport=transport) as http_client:
        hermes = HermesClient(
            base_url="http://hermes.test",
            api_key="test-key",
            http_client=http_client,
        )
        generator = StrategyProposalGenerator(hermes_client=hermes)
        with pytest.raises(ProposalValidationError, match="maximum of 2 parameter changes"):
            await generator.propose(
                parent_genome=parent,
                reflections=[],
                market_summary="Test",
            )


@pytest.mark.asyncio
async def test_empty_parameter_changes_retries_then_applies_stop() -> None:
    parent = trend_pullback_v1()
    calls = {"n": 0}

    async def mock_handler(req: httpx.Request) -> httpx.Response:
        del req
        calls["n"] += 1
        if calls["n"] == 1:
            body = {
                "hypothesis": "Needs a real mutation on the second pass.",
                "evidence_refs": ["live-market"],
                "parameter_changes": {},
            }
        else:
            body = {
                "hypothesis": "Tightening stop distance improves payoff after false breakouts.",
                "evidence_refs": ["live-market"],
                "parameter_changes": {"stop_atr_multiple": "1.2"},
            }
        return httpx.Response(
            200,
            json={
                "id": "chat-hermes-retry",
                "model": "google-antigravity/gemini-3.7-flash",
                "choices": [
                    {
                        "index": 0,
                        "message": {"role": "assistant", "content": json.dumps(body)},
                    }
                ],
            },
        )

    transport = httpx.MockTransport(mock_handler)
    async with httpx.AsyncClient(transport=transport) as http_client:
        hermes = HermesClient(
            base_url="http://hermes.test",
            api_key="test-key",
            http_client=http_client,
        )
        generator = StrategyProposalGenerator(hermes_client=hermes)
        genome = await generator.propose(
            parent_genome=parent,
            reflections=[],
            market_summary="Test",
        )

    from decimal import Decimal

    assert calls["n"] == 2
    assert genome.exit.stop_atr_multiple == Decimal("1.2")
    assert genome.exit.stop_atr_multiple < parent.exit.stop_atr_multiple
