from __future__ import annotations

from datetime import UTC, datetime, timedelta

from goldguard.context.evidence import EvidenceBundle, EvidenceDisposition, EvidenceItem, SourceKind
from goldguard.context.scoring import EvidenceGate
from goldguard.domain.enums import ExecutionMode, ProductKind
from goldguard.execution.models import MarketScope


def test_stale_or_gapped_evidence_holds_new_entries() -> None:
    now = datetime(2026, 8, 29, 12, 0, 0, tzinfo=UTC)
    item = EvidenceItem(
        evidence_id="ev-gap",
        source_kind=SourceKind.EXCHANGE,
        source_url="https://www.binance.com/en/support/announcement",
        title="Stale listing notice",
        published_at=now - timedelta(days=2),
        retrieved_at=now - timedelta(days=2),
        affected_assets=("PAXGUSDT",),
        event_class="announcements",
    )
    decision = EvidenceGate().evaluate(
        EvidenceBundle(
            scope=MarketScope(
                mode=ExecutionMode.PAPER, product=ProductKind.SPOT, symbol="PAXGUSDT"
            ),
            decision_time=now,
            items=(item,),
            disposition=EvidenceDisposition.NORMAL,
        )
    )
    assert decision.disposition is EvidenceDisposition.HOLD
    assert "STALE_EVIDENCE" in decision.reason_codes
