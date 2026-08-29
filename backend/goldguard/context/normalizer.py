from __future__ import annotations

import hashlib
import uuid
from dataclasses import dataclass
from datetime import datetime

from goldguard.context.adapters import RawEvidence
from goldguard.context.evidence import EvidenceClaim, EvidenceItem
from goldguard.context.injection import InjectionAssessment, InjectionScanner


@dataclass(frozen=True, slots=True)
class NormalizationResult:
    item: EvidenceItem
    injection: InjectionAssessment


class EvidenceNormalizer:
    def __init__(self, scanner: InjectionScanner | None = None) -> None:
        self.scanner = scanner or InjectionScanner()

    def normalize(self, raw: RawEvidence, retrieved_at: datetime) -> NormalizationResult:
        assessment = self.scanner.scan(raw.content + " " + raw.title)
        claims: list[EvidenceClaim] = []

        if not assessment.flagged:
            claims.append(
                EvidenceClaim(
                    claim_id=f"clm-{uuid.uuid4().hex[:12]}",
                    claim_text=raw.title or "Market update",
                    direction="neutral",
                    confidence=0.85,
                )
            )

        published = raw.published_at
        event = raw.event_at
        if published is None and event is None:
            published = retrieved_at

        item_id = f"ev-{hashlib.sha256((raw.source_url + raw.title).encode()).hexdigest()[:12]}"
        item = EvidenceItem(
            evidence_id=item_id,
            source_kind=raw.source_kind,
            source_url=raw.source_url,
            title=raw.title,
            published_at=published,
            event_at=event,
            retrieved_at=retrieved_at,
            affected_assets=("PAXGUSDT", "PAXG", "BTCUSDT", "ETHUSDT"),
            event_class=raw.source_section,
            claims=tuple(claims),
            raw_content_hash=hashlib.sha256(raw.content.encode()).hexdigest()[:16],
        )
        return NormalizationResult(item=item, injection=assessment)

