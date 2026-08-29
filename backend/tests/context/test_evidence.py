from __future__ import annotations

from datetime import UTC, datetime

import pytest
from goldguard.context.evidence import (
    EvidenceClaim,
    EvidenceItem,
    EvidenceScore,
    SourceKind,
)
from pydantic import ValidationError


def test_evidence_requires_publication_or_event_time() -> None:
    now = datetime(2026, 8, 29, 12, 0, 0, tzinfo=UTC)
    with pytest.raises(ValidationError, match="publication or event"):
        EvidenceItem(
            evidence_id="ev-1",
            source_kind=SourceKind.REPUTABLE_NEWS,
            source_url="https://reuters.com/article1",
            title="Fed decision",
            published_at=None,
            event_at=None,
            retrieved_at=now,
            affected_assets=("PAXGUSDT",),
            event_class="macro_monetary",
        )


def test_evidence_claim_and_score() -> None:
    claim = EvidenceClaim(
        claim_id="c-1",
        claim_text="Fed holds rate steady",
        direction="neutral",
        confidence=0.90,
    )
    assert claim.claim_hash != ""

    score = EvidenceScore(
        reliability=0.9,
        freshness=0.8,
        relevance=0.85,
        agreement=0.95,
    )
    assert score.overall > 0.8

