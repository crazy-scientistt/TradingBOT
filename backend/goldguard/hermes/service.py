from dataclasses import dataclass

from pydantic import ValidationError

from goldguard.hermes.models import EvaluationPartition, StrategyProposal


class ProposalRejected(ValueError):
    """A proposal that failed the core service's declarative boundary."""


class HoldoutEmbargoed(PermissionError):
    """Untouched holdout evidence cannot be inspected before freezing."""


@dataclass(frozen=True)
class ProposalRecord:
    proposal: StrategyProposal
    frozen: bool = False

    @property
    def proposal_id(self) -> str:
        return self.proposal.proposal_id


class ProposalService:
    """Stores immutable proposals; intentionally exposes no activation operation."""

    def __init__(
        self,
        *,
        active_parent_version: str,
        evidence_catalog: set[str],
        maximum_payload_bytes: int = 16_384,
    ) -> None:
        self._active_parent_version = active_parent_version
        self._evidence_catalog = frozenset(evidence_catalog)
        self._maximum_payload_bytes = maximum_payload_bytes
        self._records: dict[str, ProposalRecord] = {}

    def submit(self, payload: bytes) -> StrategyProposal:
        if len(payload) > self._maximum_payload_bytes:
            raise ProposalRejected("proposal payload is too large")
        try:
            proposal = StrategyProposal.model_validate_json(payload)
        except ValidationError as error:
            raise ProposalRejected("proposal schema is invalid") from error
        if proposal.proposal_id in self._records:
            raise ProposalRejected("proposal id was already submitted")
        if proposal.parent_version != self._active_parent_version:
            raise ProposalRejected("proposal parent version is not active")
        unknown_evidence = set(proposal.evidence_refs) - self._evidence_catalog
        if unknown_evidence:
            raise ProposalRejected("proposal cites unknown evidence")
        self._records[proposal.proposal_id] = ProposalRecord(proposal)
        return proposal

    def freeze_for_holdout(self, proposal_id: str) -> ProposalRecord:
        current = self._record(proposal_id)
        frozen = ProposalRecord(current.proposal, frozen=True)
        self._records[proposal_id] = frozen
        return frozen

    def evaluation_view(
        self,
        proposal_id: str,
        partition: EvaluationPartition,
    ) -> ProposalRecord:
        record = self._record(proposal_id)
        if partition == EvaluationPartition.HOLDOUT and not record.frozen:
            raise HoldoutEmbargoed("holdout remains sealed until proposal freeze")
        return record

    def _record(self, proposal_id: str) -> ProposalRecord:
        try:
            return self._records[proposal_id]
        except KeyError as error:
            raise ProposalRejected("unknown proposal id") from error
