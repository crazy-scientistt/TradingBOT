from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter

from goldguard.release.qualification import SystemQualificationService

router = APIRouter(prefix="/api/qualification", tags=["qualification"])

_qualification_service = SystemQualificationService()


@router.get("/report")
def get_qualification_report() -> dict[str, Any]:
    now = datetime.now(UTC)
    report = _qualification_service.evaluate(now)
    return {
        "ready_for_live_canary": report.ready_for_live_canary,
        "evaluated_at": report.evaluated_at,
        "gates": report.gates,
        "blockers": list(report.blockers),
        "report_hash": report.report_hash,
    }

