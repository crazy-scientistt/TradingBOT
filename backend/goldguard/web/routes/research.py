from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, HTTPException, Query

from goldguard.domain.enums import ExecutionMode, ProductKind
from goldguard.execution.models import MarketScope
from goldguard.services.evidence_service import EvidenceService
from goldguard.storage.evidence_repository import EvidenceRepository
from goldguard.web.schemas.research import (
    ResearchEnvelope,
)

router = APIRouter(prefix="/api/research", tags=["research"])

_evidence_service: EvidenceService | None = None


def configure_evidence_service(service: EvidenceService) -> None:
    global _evidence_service
    _evidence_service = service


def get_evidence_service() -> EvidenceService:
    global _evidence_service
    if _evidence_service is None:
        from goldguard.web import app as app_module

        if app_module._db is not None:
            repo = EvidenceRepository(app_module._db)
            _evidence_service = EvidenceService(repo)
        else:
            raise HTTPException(status_code=503, detail="database not ready")
    return _evidence_service


@router.get("/evidence", response_model=ResearchEnvelope)
def get_research_evidence(
    product: str = Query(default="spot"),
    symbol: str = Query(default="PAXGUSDT"),
) -> dict[str, Any]:
    now = datetime.now(UTC)
    prod = ProductKind.FUTURES if product.lower() == "futures" else ProductKind.SPOT
    scope = MarketScope(mode=ExecutionMode.PAPER, product=prod, symbol=symbol)

    try:
        service = get_evidence_service()
        bundle = service.bundle(scope, now)
    except Exception:
        return {
            "availability": "unavailable",
            "source": "evidence_service",
            "observed_at": now.isoformat(),
            "stale": True,
            "detail": "evidence service unavailable",
            "data": None,
        }

    if not bundle.items:
        return {
            "availability": "unavailable",
            "source": "evidence_service",
            "observed_at": now.isoformat(),
            "stale": False,
            "detail": "no evidence captured yet",
            "data": None,
        }

    items = [
        {
            "evidence_id": item.evidence_id,
            "source_kind": item.source_kind.value,
            "source_url": item.source_url,
            "title": item.title,
            "published_at": item.published_at.isoformat() if item.published_at else None,
            "event_at": item.event_at.isoformat() if item.event_at else None,
            "retrieved_at": item.retrieved_at.isoformat(),
            "affected_assets": list(item.affected_assets),
            "event_class": item.event_class,
        }
        for item in bundle.items
    ]

    return {
        "availability": "available",
        "source": "evidence_service",
        "observed_at": now.isoformat(),
        "stale": False,
        "detail": None,
        "data": {
            "product": product,
            "symbol": symbol,
            "disposition": bundle.disposition.value,
            "overall_score": bundle.overall_score,
            "items": items,
        },
    }


@router.get("/health")
def get_research_health() -> dict[str, Any]:
    service = get_evidence_service()
    return service.health()

