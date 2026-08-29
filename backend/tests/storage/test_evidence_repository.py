from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from goldguard.context.evidence import (
    EvidenceItem,
    SourceKind,
)
from goldguard.domain.enums import ExecutionMode, ProductKind
from goldguard.execution.models import MarketScope
from goldguard.storage.database import Database
from goldguard.storage.evidence_repository import EvidenceRepository


def test_bundle_uses_only_information_available_at_decision_time(tmp_path: Path) -> None:
    db = Database(tmp_path / "evidence_test.db")
    db.migrate()
    repo = EvidenceRepository(db)

    item = EvidenceItem(
        evidence_id="ev-1",
        source_kind=SourceKind.OFFICIAL,
        source_url="https://federalreserve.gov/release",
        title="FOMC Statement",
        published_at=datetime(2026, 8, 28, 10, 0, 0, tzinfo=UTC),
        retrieved_at=datetime(2026, 8, 28, 10, 5, 0, tzinfo=UTC),
        affected_assets=("PAXGUSDT", "PAXG", "USDT"),
        event_class="fomc_statement",
    )
    repo.upsert(item)

    scope = MarketScope(mode=ExecutionMode.PAPER, product=ProductKind.SPOT, symbol="PAXGUSDT")

    # Decision at 10:00:00 (before retrieved_at 10:05:00) -> empty items
    bundle_before = repo.bundle_for(scope, datetime(2026, 8, 28, 10, 0, 0, tzinfo=UTC))
    assert bundle_before.items == ()

    # Decision at 10:10:00 (after retrieved_at) -> 1 item returned
    bundle_after = repo.bundle_for(scope, datetime(2026, 8, 28, 10, 10, 0, tzinfo=UTC))
    assert len(bundle_after.items) == 1
    assert bundle_after.items[0].evidence_id == "ev-1"

