from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

from goldguard.context.evidence import (
    EvidenceBundle,
    EvidenceClaim,
    EvidenceDisposition,
    EvidenceItem,
    SourceKind,
)
from goldguard.context.scoring import EvidenceGate
from goldguard.domain.enums import ExecutionMode, ProductKind
from goldguard.execution.models import MarketScope


def test_conflicting_high_quality_claims_reduce_size() -> None:
    now = datetime(2026, 8, 29, 12, 0, 0, tzinfo=UTC)
    scope = MarketScope(mode=ExecutionMode.PAPER, product=ProductKind.SPOT, symbol="PAXGUSDT")

    item1 = EvidenceItem(
        evidence_id="ev-1",
        source_kind=SourceKind.OFFICIAL,
        source_url="https://fed.gov/1",
        title="Bullish indicator",
        published_at=now,
        retrieved_at=now,
        affected_assets=("PAXGUSDT",),
        event_class="fed",
        claims=(
            EvidenceClaim(
                claim_id="c-1",
                claim_text="Inflation up",
                direction="bullish",
                confidence=0.9,
            ),
            EvidenceClaim(
                claim_id="c-2",
                claim_text="Rates cut",
                direction="bearish",
                confidence=0.9,
            ),
            EvidenceClaim(
                claim_id="c-3",
                claim_text="Neutral stance",
                direction="neutral",
                confidence=0.9,
            ),
        ),
    )

    bundle = EvidenceBundle(
        scope=scope,
        decision_time=now,
        items=(item1,),
        disposition=EvidenceDisposition.NORMAL,
        overall_score=0.9,
    )

    gate = EvidenceGate()
    decision = gate.evaluate(bundle)
    assert decision.disposition == EvidenceDisposition.REDUCED_SIZE
    assert Decimal("0") < decision.size_multiplier < Decimal("1")
