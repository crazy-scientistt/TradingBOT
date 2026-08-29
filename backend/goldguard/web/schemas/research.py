from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class ResearchEvidenceItem(BaseModel):
    model_config = ConfigDict(extra="forbid")
    evidence_id: str
    source_kind: str
    source_url: str
    title: str
    published_at: str | None = None
    event_at: str | None = None
    retrieved_at: str
    affected_assets: list[str]
    event_class: str


class ResearchEvidenceData(BaseModel):
    model_config = ConfigDict(extra="forbid")
    product: str
    symbol: str
    disposition: str
    overall_score: float
    items: list[ResearchEvidenceItem]


class ResearchEnvelope(BaseModel):
    model_config = ConfigDict(extra="forbid")
    availability: str
    source: str
    observed_at: str
    stale: bool
    detail: str | None = None
    data: ResearchEvidenceData | None = None

