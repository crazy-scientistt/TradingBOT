from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest
from goldguard.domain.enums import ExecutionMode, ProductKind
from goldguard.execution.models import MarketScope
from goldguard.services.evidence_service import EvidenceService
from goldguard.storage.database import Database
from goldguard.storage.evidence_repository import EvidenceRepository


@pytest.mark.asyncio
async def test_evidence_service_refresh_and_bundle(tmp_path: Path) -> None:
    db = Database(tmp_path / "evidence_service_test.db")
    db.migrate()
    repo = EvidenceRepository(db)
    service = EvidenceService(repository=repo)

    ingested = await service.refresh_due()
    assert ingested >= 1

    scope = MarketScope(mode=ExecutionMode.PAPER, product=ProductKind.SPOT, symbol="PAXGUSDT")
    bundle = service.bundle(scope, datetime.now(UTC))
    assert len(bundle.items) >= 1

    health = service.health()
    assert health["status"] == "healthy"

