from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from goldguard.context.adapters import EvidenceAdapter
from goldguard.context.adapters.binance_announcements import BinanceAnnouncementsAdapter
from goldguard.context.adapters.forex_factory import ForexFactoryAdapter
from goldguard.context.adapters.official_releases import OfficialReleasesAdapter
from goldguard.context.evidence import EvidenceBundle
from goldguard.context.normalizer import EvidenceNormalizer
from goldguard.context.scoring import EvidenceGate, EvidenceScorer
from goldguard.execution.models import MarketScope
from goldguard.storage.evidence_repository import EvidenceRepository


class EvidenceService:
    def __init__(
        self,
        repository: EvidenceRepository,
        normalizer: EvidenceNormalizer | None = None,
        scorer: EvidenceScorer | None = None,
        gate: EvidenceGate | None = None,
    ) -> None:
        self.repository = repository
        self.normalizer = normalizer or EvidenceNormalizer()
        self.scorer = scorer or EvidenceScorer()
        self.gate = gate or EvidenceGate()
        self.adapters: list[EvidenceAdapter] = [
            BinanceAnnouncementsAdapter(),
            ForexFactoryAdapter(),
            OfficialReleasesAdapter(),
        ]
        self._last_refresh: dict[str, str] = {}
        self._failed_adapters: set[str] = set()

    def fail_adapter(self, adapter_name: str) -> None:
        self._failed_adapters.add(adapter_name)

    async def refresh_due(self) -> int:
        now = datetime.now(UTC)
        total_ingested = 0
        for adapter in self.adapters:
            if adapter.name in self._failed_adapters:
                continue
            try:
                raw_items = await adapter.fetch(now)
                for raw in raw_items:
                    res = self.normalizer.normalize(raw, now)
                    self.repository.upsert(res.item)
                    total_ingested += 1
                self._last_refresh[adapter.name] = now.isoformat()
            except Exception:
                pass
        return total_ingested

    def bundle(self, scope: MarketScope, decision_time: datetime) -> EvidenceBundle:
        return self.repository.bundle_for(scope, decision_time)

    def health(self) -> dict[str, Any]:
        return {
            "status": "healthy" if not self._failed_adapters else "degraded",
            "adapters": [
                {
                    "name": a.name,
                    "status": "fail" if a.name in self._failed_adapters else "active",
                    "last_refresh": self._last_refresh.get(a.name),
                }
                for a in self.adapters
            ],
        }

