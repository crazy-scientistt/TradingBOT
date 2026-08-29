from __future__ import annotations

import json
from datetime import datetime

from goldguard.context.evidence import (
    EvidenceBundle,
    EvidenceClaim,
    EvidenceDisposition,
    EvidenceItem,
    SourceKind,
)
from goldguard.execution.models import MarketScope
from goldguard.storage.database import Database


class EvidenceRepository:
    def __init__(self, database: Database) -> None:
        self.database = database

    def upsert(self, item: EvidenceItem) -> None:
        claims_data = [
            {
                "claim_id": c.claim_id,
                "claim_text": c.claim_text,
                "direction": c.direction,
                "confidence": c.confidence,
                "claim_hash": c.claim_hash,
            }
            for c in item.claims
        ]
        with self.database.transaction() as tx:
            tx.execute(
                "INSERT OR REPLACE INTO evidence_items "
                "(evidence_id, source_kind, source_url, title, published_at, event_at, "
                "retrieved_at, affected_assets_json, event_class, claims_json, raw_content_hash) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    item.evidence_id,
                    item.source_kind.value,
                    str(item.source_url),
                    item.title,
                    item.published_at.isoformat() if item.published_at else None,
                    item.event_at.isoformat() if item.event_at else None,
                    item.retrieved_at.isoformat(),
                    json.dumps(list(item.affected_assets)),
                    item.event_class,
                    json.dumps(claims_data),
                    item.raw_content_hash,
                ),
            )

    def latest(
        self, asset: str, event_class: str, now: datetime
    ) -> list[EvidenceItem]:
        iso_now = now.isoformat()
        with self.database.connect() as conn:
            rows = conn.execute(
                "SELECT * FROM evidence_items "
                "WHERE event_class = ? AND retrieved_at <= ? "
                "ORDER BY retrieved_at DESC LIMIT 50",
                (event_class, iso_now),
            ).fetchall()

            results: list[EvidenceItem] = []
            for r in rows:
                assets = json.loads(str(r["affected_assets_json"]))
                if asset in assets or not assets:
                    claims_raw = json.loads(str(r["claims_json"]))
                    claims = tuple(
                        EvidenceClaim(
                            claim_id=c["claim_id"],
                            claim_text=c["claim_text"],
                            direction=c["direction"],
                            confidence=float(c["confidence"]),
                            claim_hash=c["claim_hash"],
                        )
                        for c in claims_raw
                    )
                    pub = (
                        datetime.fromisoformat(str(r["published_at"]))
                        if r["published_at"]
                        else None
                    )
                    evt = (
                        datetime.fromisoformat(str(r["event_at"]))
                        if r["event_at"]
                        else None
                    )
                    results.append(
                        EvidenceItem(
                            evidence_id=str(r["evidence_id"]),
                            source_kind=SourceKind(str(r["source_kind"])),
                            source_url=str(r["source_url"]),
                            title=str(r["title"]),
                            published_at=pub,
                            event_at=evt,
                            retrieved_at=datetime.fromisoformat(str(r["retrieved_at"])),
                            affected_assets=tuple(assets),
                            event_class=str(r["event_class"]),
                            claims=claims,
                            raw_content_hash=str(r["raw_content_hash"]),
                        )
                    )
            return results

    def bundle_for(
        self, scope: MarketScope, decision_time: datetime
    ) -> EvidenceBundle:
        iso_time = decision_time.isoformat()
        with self.database.connect() as conn:
            rows = conn.execute(
                "SELECT * FROM evidence_items "
                "WHERE retrieved_at <= ? ORDER BY retrieved_at DESC LIMIT 50",
                (iso_time,),
            ).fetchall()

            matching: list[EvidenceItem] = []
            for r in rows:
                assets = json.loads(str(r["affected_assets_json"]))
                base_asset = scope.symbol.replace("USDT", "")
                if scope.symbol in assets or base_asset in assets or not assets:
                    claims_raw = json.loads(str(r["claims_json"]))
                    claims = tuple(
                        EvidenceClaim(
                            claim_id=c["claim_id"],
                            claim_text=c["claim_text"],
                            direction=c["direction"],
                            confidence=float(c["confidence"]),
                            claim_hash=c["claim_hash"],
                        )
                        for c in claims_raw
                    )
                    pub = (
                        datetime.fromisoformat(str(r["published_at"]))
                        if r["published_at"]
                        else None
                    )
                    evt = (
                        datetime.fromisoformat(str(r["event_at"]))
                        if r["event_at"]
                        else None
                    )
                    matching.append(
                        EvidenceItem(
                            evidence_id=str(r["evidence_id"]),
                            source_kind=SourceKind(str(r["source_kind"])),
                            source_url=str(r["source_url"]),
                            title=str(r["title"]),
                            published_at=pub,
                            event_at=evt,
                            retrieved_at=datetime.fromisoformat(str(r["retrieved_at"])),
                            affected_assets=tuple(assets),
                            event_class=str(r["event_class"]),
                            claims=claims,
                            raw_content_hash=str(r["raw_content_hash"]),
                        )
                    )

            disposition = (
                EvidenceDisposition.NORMAL if matching else EvidenceDisposition.HOLD
            )
            return EvidenceBundle(
                scope=scope,
                decision_time=decision_time,
                items=tuple(matching),
                disposition=disposition,
                overall_score=1.0 if matching else 0.0,
            )

