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
from goldguard.context.injection import InjectionScanner
from goldguard.execution.models import MarketScope

COMMENTARY_EVENT_CLASSES = frozenset({"forum", "thread", "commentary"})
AUTHORITATIVE_KINDS = frozenset(
    {
        SourceKind.OFFICIAL,
        SourceKind.EXCHANGE,
        SourceKind.CALENDAR,
        SourceKind.REPUTABLE_NEWS,
    }
)


class EvidenceScorer:
    def score(self, item: EvidenceItem, scope: MarketScope, now: datetime) -> EvidenceScore:
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

        if item.event_class.lower() in COMMENTARY_EVENT_CLASSES:
            reliability = min(reliability, 0.35)

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


def _aware(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _is_authoritative(item: EvidenceItem) -> bool:
    if item.event_class.lower() in COMMENTARY_EVENT_CLASSES:
        return False
    if item.source_kind == SourceKind.WEB_SEARCH:
        return False
    return item.source_kind in AUTHORITATIVE_KINDS


class EvidenceGate:
    def __init__(self, scanner: InjectionScanner | None = None) -> None:
        self.scanner = scanner or InjectionScanner()

    def evaluate(self, bundle: EvidenceBundle, opportunity: Any = None) -> EvidenceDecision:
        _ = opportunity
        if not bundle.items:
            return EvidenceDecision(
                disposition=EvidenceDisposition.HOLD,
                size_multiplier=Decimal("0"),
                reason_codes=("NO_EVIDENCE_AVAILABLE",),
            )

        for item in bundle.items:
            blob = item.title + " " + " ".join(claim.claim_text for claim in item.claims)
            if self.scanner.scan(blob).flagged:
                return EvidenceDecision(
                    disposition=EvidenceDisposition.HOLD,
                    size_multiplier=Decimal("0"),
                    reason_codes=("INJECTED_EVIDENCE",),
                )

        now = _aware(bundle.decision_time)
        fresh = False
        for item in bundle.items:
            stamp = item.published_at or item.event_at or item.retrieved_at
            if now - _aware(stamp) <= timedelta(hours=24):
                fresh = True
                break
        if not fresh:
            return EvidenceDecision(
                disposition=EvidenceDisposition.HOLD,
                size_multiplier=Decimal("0"),
                reason_codes=("STALE_EVIDENCE",),
            )

        if not any(_is_authoritative(item) for item in bundle.items):
            return EvidenceDecision(
                disposition=EvidenceDisposition.HOLD,
                size_multiplier=Decimal("0"),
                reason_codes=("INDEPENDENT_SOURCE_MISSING",),
            )

        has_conflicts = len({c.direction for item in bundle.items for c in item.claims}) > 2
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
