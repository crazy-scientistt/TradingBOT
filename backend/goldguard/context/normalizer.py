from __future__ import annotations

import hashlib
import uuid
from dataclasses import dataclass
from datetime import datetime

from goldguard.context.adapters import RawEvidence
from goldguard.context.evidence import EvidenceClaim, EvidenceItem
from goldguard.context.injection import InjectionAssessment, InjectionScanner

KNOWN_ASSETS = ("PAXGUSDT", "PAXG", "BTCUSDT", "ETHUSDT", "XAUUSD")


@dataclass(frozen=True, slots=True)
class NormalizationResult:
    item: EvidenceItem | None
    injection: InjectionAssessment
    skipped_reason: str | None = None


class EvidenceNormalizer:
    def __init__(self, scanner: InjectionScanner | None = None) -> None:
        self.scanner = scanner or InjectionScanner()

    def normalize(self, raw: RawEvidence, retrieved_at: datetime) -> NormalizationResult:
        assessment = self.scanner.scan(raw.content + " " + raw.title)
        if raw.published_at is None and raw.event_at is None:
            return NormalizationResult(
                item=None,
                injection=assessment,
                skipped_reason="TIMESTAMP_MISSING",
            )

        claims: list[EvidenceClaim] = []
        if not assessment.flagged:
            claims.append(
                EvidenceClaim(
                    claim_id=f"clm-{uuid.uuid4().hex[:12]}",
                    claim_text=raw.title or "Market update",
                    direction="neutral",
                    confidence=0.5,
                )
            )

        blob = f"{raw.title} {raw.content} {raw.source_url}".upper()
        assets = tuple(asset for asset in KNOWN_ASSETS if asset in blob)

        item_id = f"ev-{hashlib.sha256((raw.source_url + raw.title).encode()).hexdigest()[:12]}"
        item = EvidenceItem(
            evidence_id=item_id,
            source_kind=raw.source_kind,
            source_url=raw.source_url,
            title=raw.title,
            published_at=raw.published_at,
            event_at=raw.event_at,
            retrieved_at=retrieved_at,
            affected_assets=assets,
            event_class=raw.source_section,
            claims=tuple(claims),
            raw_content_hash=hashlib.sha256(raw.content.encode()).hexdigest()[:16],
        )
        return NormalizationResult(item=item, injection=assessment)
