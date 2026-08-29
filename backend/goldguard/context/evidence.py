from __future__ import annotations

import hashlib
from datetime import UTC, datetime
from enum import StrEnum
from typing import Self

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from goldguard.execution.models import MarketScope


class SourceKind(StrEnum):
    OFFICIAL = "official"
    EXCHANGE = "exchange"
    REPUTABLE_NEWS = "reputable_news"
    CALENDAR = "calendar"
    WEB_SEARCH = "web_search"


class EvidenceDisposition(StrEnum):
    NORMAL = "normal"
    REDUCED_SIZE = "reduced_size"
    HOLD = "hold"
    REJECTED = "rejected"


class EvidenceClaim(BaseModel):
    model_config = ConfigDict(frozen=True)
    claim_id: str
    claim_text: str
    direction: str  # "bullish", "bearish", "neutral", "mixed"
    confidence: float = Field(ge=0.0, le=1.0)
    claim_hash: str = ""

    @model_validator(mode="after")
    def compute_hash(self) -> Self:
        if not self.claim_hash:
            h = hashlib.sha256(f"{self.claim_text}:{self.direction}".encode()).hexdigest()[:16]
            object.__setattr__(self, "claim_hash", h)
        return self


class EvidenceScore(BaseModel):
    model_config = ConfigDict(frozen=True)
    reliability: float = Field(ge=0.0, le=1.0)
    freshness: float = Field(ge=0.0, le=1.0)
    relevance: float = Field(ge=0.0, le=1.0)
    agreement: float = Field(ge=0.0, le=1.0)

    @property
    def overall(self) -> float:
        return (
            self.reliability * 0.35
            + self.freshness * 0.25
            + self.relevance * 0.25
            + self.agreement * 0.15
        )


class EvidenceItem(BaseModel):
    model_config = ConfigDict(frozen=True)
    evidence_id: str
    source_kind: SourceKind
    source_url: str
    title: str
    published_at: datetime | None = None
    event_at: datetime | None = None
    retrieved_at: datetime
    affected_assets: tuple[str, ...] = Field(default_factory=tuple)
    event_class: str
    claims: tuple[EvidenceClaim, ...] = Field(default_factory=tuple)
    raw_content_hash: str = ""

    @field_validator("published_at", "event_at", "retrieved_at")
    @classmethod
    def validate_utc(cls, value: datetime | None) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None:
            return value.replace(tzinfo=UTC)
        return value.astimezone(UTC)

    @model_validator(mode="after")
    def validate_temporal_provenance(self) -> Self:
        if self.published_at is None and self.event_at is None:
            raise ValueError("evidence item requires at least a publication or event timestamp")
        if not self.raw_content_hash:
            raw = f"{self.source_url}:{self.title}:{self.retrieved_at.isoformat()}"
            object.__setattr__(
                self, "raw_content_hash", hashlib.sha256(raw.encode()).hexdigest()[:16]
            )
        return self


class EvidenceBundle(BaseModel):
    model_config = ConfigDict(frozen=True)
    scope: MarketScope
    decision_time: datetime
    items: tuple[EvidenceItem, ...] = Field(default_factory=tuple)
    disposition: EvidenceDisposition = EvidenceDisposition.NORMAL
    overall_score: float = 1.0

