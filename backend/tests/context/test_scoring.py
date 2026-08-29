from __future__ import annotations

from datetime import UTC, datetime

from goldguard.context.evidence import (
    EvidenceBundle,
    EvidenceDisposition,
    EvidenceItem,
    SourceKind,
)
from goldguard.context.scoring import EvidenceGate, EvidenceScorer
from goldguard.domain.enums import ExecutionMode, ProductKind
from goldguard.execution.models import MarketScope


def test_evidence_scoring_and_gate() -> None:
    now = datetime(2026, 8, 29, 12, 0, 0, tzinfo=UTC)
    scorer = EvidenceScorer()
    scope = MarketScope(mode=ExecutionMode.PAPER, product=ProductKind.SPOT, symbol="PAXGUSDT")

    item = EvidenceItem(
        evidence_id="ev-1",
        source_kind=SourceKind.OFFICIAL,
        source_url="https://federalreserve.gov/release",
        title="FOMC Statement",
        published_at=now,
        retrieved_at=now,
        affected_assets=("PAXGUSDT",),
        event_class="fomc_statement",
    )
    score = scorer.score(item, scope, now)
    assert score.reliability == 1.0
    assert score.freshness == 1.0

    gate = EvidenceGate()
    bundle = EvidenceBundle(
        scope=scope,
        decision_time=now,
        items=(item,),
        disposition=EvidenceDisposition.NORMAL,
        overall_score=score.overall,
    )
    dec = gate.evaluate(bundle)
    assert dec.disposition == EvidenceDisposition.NORMAL
    assert dec.size_multiplier == 1.0

