import pytest
from goldguard.hermes.generator import ProposalValidationError, StrategyProposalGenerator
from goldguard.strategy.genome import trend_pullback_v1


@pytest.mark.asyncio
async def test_hermes_unavailable_does_not_fall_back_to_opencodex() -> None:
    generator = StrategyProposalGenerator(gateway_client=None, hermes_client=None)
    with pytest.raises(ProposalValidationError, match="HERMES_UNAVAILABLE"):
        await generator.propose(
            parent_genome=trend_pullback_v1(),
            reflections=[],
            market_summary="n/a",
        )
