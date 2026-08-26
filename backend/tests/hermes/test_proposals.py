import json
from decimal import Decimal

import pytest
from goldguard.hermes.models import StrategyChange, StrategyProposal
from goldguard.hermes.service import ProposalRejected, ProposalService
from pydantic import ValidationError


def proposal_payload(**overrides: object) -> bytes:
    payload: dict[str, object] = {
        "proposal_id": "proposal-001",
        "parent_version": "safe-default-v1",
        "title": "Require stronger recovery volume",
        "rationale": "Historical losing pullbacks clustered in low-participation periods.",
        "evidence_refs": ["report-development-1", "trade-cluster-7"],
        "change": {
            "parameter": "minimum_volume_ratio",
            "value": "0.95",
        },
    }
    payload.update(overrides)
    return json.dumps(payload).encode()


def test_proposal_allows_exactly_one_bounded_declarative_change() -> None:
    proposal = StrategyProposal.model_validate_json(proposal_payload())

    assert proposal.change == StrategyChange(
        parameter="minimum_volume_ratio",
        value=Decimal("0.95"),
    )


@pytest.mark.parametrize(
    "change",
    [
        {"parameter": "risk_per_trade", "value": "0.02"},
        {"parameter": "reward_r_multiple", "value": "10"},
        {"parameter": "minimum_volume_ratio", "value": 0.95},
        {"parameter": "minimum_volume_ratio", "value": "0.95", "shell": "curl x"},
    ],
)
def test_proposal_rejects_unsafe_unknown_float_or_executable_changes(
    change: dict[str, object],
) -> None:
    with pytest.raises(ValidationError):
        StrategyProposal.model_validate_json(proposal_payload(change=change))


def test_service_rejects_wrong_parent_unknown_evidence_replay_and_oversize() -> None:
    service = ProposalService(
        active_parent_version="safe-default-v1",
        evidence_catalog={"report-development-1", "trade-cluster-7"},
        maximum_payload_bytes=2_000,
    )

    accepted = service.submit(proposal_payload())
    assert accepted.proposal_id == "proposal-001"
    with pytest.raises(ProposalRejected, match="already submitted"):
        service.submit(proposal_payload())
    with pytest.raises(ProposalRejected, match="parent version"):
        service.submit(proposal_payload(proposal_id="proposal-002", parent_version="old-v0"))
    with pytest.raises(ProposalRejected, match="unknown evidence"):
        service.submit(
            proposal_payload(proposal_id="proposal-003", evidence_refs=["future-holdout"])
        )
    with pytest.raises(ProposalRejected, match="payload is too large"):
        service.submit(b"x" * 2_001)
