from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any

from goldguard.context.evidence import (
    EvidenceBundle,
    EvidenceDisposition,
    EvidenceItem,
    EvidenceScore,
    SourceKind,
)
from goldguard.execution.models import MarketScope


class EvidenceScorer:
    def score(self, item: EvidenceItem, scope: MarketScope, now: datetime) -> EvidenceScore:
        # Reliability by source kind
        if item.source_kind == SourceKind.OFFICIAL:
            reliability = 1.0
        elif item.source_kind == SourceKind.EXCHANGE:
            reliability = 0.95
        elif item.source_kind == SourceKind.CALENDAR:
            reliability = 0.90
        elif item.source_kind == SourceKind.REPUTABLE_NEWS:
            reliability = 0.80
        else:
            reliability = 0.50

        # Freshness
        observed = item.published_at or item.event_at or item.retrieved_at
        if observed.tzinfo is None:
            observed = observed.replace(tzinfo=UTC)
        if now.tzinfo is None:
            now = now.replace(tzinfo=UTC)
        age = now - observed
        if age <= timedelta(hours=1):
            freshness = 1.0
        elif age <= timedelta(hours=6):
            freshness = 0.8
        elif age <= timedelta(hours=24):
            freshness = 0.5
        else:
            freshness = 0.2

        relevance = 0.9 if scope.symbol in item.affected_assets else 0.7
        agreement = 0.9

        return EvidenceScore(
            reliability=reliability,
            freshness=freshness,
            relevance=relevance,
            agreement=agreement,
        )


class EvidenceGate:
    def evaluate(self, bundle: EvidenceBundle, opportunity: Any = None) -> Any:
        if not bundle.items:
            return EvidenceDecision(
                disposition=EvidenceDisposition.HOLD,
                size_multiplier=Decimal("0"),
                reason_codes=("NO_EVIDENCE_AVAILABLE",),
            )

        has_conflicts = len(set(c.direction for item in bundle.items for c in item.claims)) > 2
        if has_conflicts:
            return EvidenceDecision(
                disposition=EvidenceDisposition.REDUCED_SIZE,
                size_multiplier=Decimal("0.5"),
                reason_codes=("CONFLICTING_CLAIMS_REDUCED_SIZE",),
            )

        return EvidenceDecision(
            disposition=EvidenceDisposition.NORMAL,
            size_multiplier=Decimal("1.0"),
            reason_codes=("EVIDENCE_VERIFIED",),
        )


class EvidenceDecision:
    def __init__(
        self,
        disposition: EvidenceDisposition,
        size_multiplier: Decimal,
        reason_codes: tuple[str, ...],
    ) -> None:
        self.disposition = disposition
        self.size_multiplier = size_multiplier
        self.reason_codes = reason_codes

