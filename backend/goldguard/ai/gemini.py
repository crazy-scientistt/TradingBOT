import hashlib
import json
from dataclasses import asdict, dataclass
from typing import Any

import httpx
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from goldguard.ai.prompts import DECISION_SYSTEM_PROMPT
from goldguard.domain.enums import AiDecision, CandidateAction
from goldguard.domain.models import ai_decision_is_compatible

KNOWN_REASON_CODES = frozenset(
    {
        "TREND_ALIGNED",
        "TREND_FRAGILE",
        "NEWS_SUPPORTIVE",
        "NEWS_RISK",
        "MACRO_EVENT_RISK",
        "LIQUIDITY_GOOD",
        "LIQUIDITY_WEAK",
        "CONTEXT_CONFLICT",
        "MEMORY_SUPPORTIVE",
        "MEMORY_CAUTION",
        "REGIME_INVALIDATION",
        "RISK_REDUCTION",
    }
)


RESPONSE_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "decision": {
            "type": "string",
            "enum": ["APPROVE_ENTRY", "REJECT_ENTRY", "EXIT", "HOLD"],
        },
        "confidence": {"type": "integer", "minimum": 0, "maximum": 100},
        "reason_codes": {"type": "array", "items": {"type": "string"}, "maxItems": 8},
        "rationale": {"type": "string", "maxLength": 500},
        "memory_refs": {"type": "array", "items": {"type": "string"}, "maxItems": 3},
    },
    "required": ["decision", "confidence", "reason_codes", "rationale", "memory_refs"],
}


@dataclass(frozen=True)
class DecisionRequest:
    candidate: CandidateAction
    strategy_version: str
    features: dict[str, object]
    context: dict[str, object]
    memory_summaries: tuple[dict[str, object], ...]


@dataclass(frozen=True)
class AiAssessment:
    decision: AiDecision
    confidence: int
    reason_codes: tuple[str, ...]
    rationale: str
    memory_refs: tuple[str, ...]
    prompt_hash: str
    model: str


class _ValidatedResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    decision: AiDecision
    confidence: int = Field(ge=0, le=100)
    reason_codes: tuple[str, ...] = Field(max_length=8)
    rationale: str = Field(min_length=1, max_length=500)
    memory_refs: tuple[str, ...] = Field(max_length=3)


class GeminiDecisionClient:
    def __init__(
        self,
        *,
        api_key: str,
        model: str,
        http_client: httpx.AsyncClient,
        minimum_confidence: int,
        base_url: str = "https://generativelanguage.googleapis.com/v1beta",
    ) -> None:
        self.api_key = api_key
        self.model = model
        self.http_client = http_client
        self.minimum_confidence = minimum_confidence
        self.base_url = base_url.rstrip("/")

    async def decide(self, request: DecisionRequest) -> AiAssessment:
        prompt_material = json.dumps(
            asdict(request),
            sort_keys=True,
            default=str,
            separators=(",", ":"),
        )
        prompt_hash = hashlib.sha256(prompt_material.encode()).hexdigest()
        payload = {
            "systemInstruction": {"parts": [{"text": DECISION_SYSTEM_PROMPT}]},
            "contents": [
                {
                    "role": "user",
                    "parts": [{"text": prompt_material}],
                }
            ],
            "generationConfig": {
                "temperature": 0,
                "responseMimeType": "application/json",
                "responseSchema": RESPONSE_SCHEMA,
            },
        }
        try:
            response = await self.http_client.post(
                f"{self.base_url}/models/{self.model}:generateContent",
                headers={"x-goog-api-key": self.api_key, "content-type": "application/json"},
                json=payload,
                timeout=15,
            )
            response.raise_for_status()
        except (httpx.TimeoutException, httpx.NetworkError, httpx.HTTPStatusError):
            return self._safe_failure(request, prompt_hash, "MODEL_UNAVAILABLE")

        try:
            body = response.json()
            raw_text = body["candidates"][0]["content"]["parts"][0]["text"]
            parsed = _ValidatedResponse.model_validate_json(raw_text)
        except (KeyError, IndexError, TypeError, ValueError, ValidationError):
            return self._safe_failure(request, prompt_hash, "INVALID_AI_RESPONSE")
        if any(code not in KNOWN_REASON_CODES for code in parsed.reason_codes):
            return self._safe_failure(request, prompt_hash, "INVALID_AI_RESPONSE")
        if not ai_decision_is_compatible(request.candidate, parsed.decision):
            return self._safe_failure(request, prompt_hash, "INCOMPATIBLE_AI_DECISION")
        if (
            parsed.decision is AiDecision.APPROVE_ENTRY
            and parsed.confidence < self.minimum_confidence
        ):
            return self._safe_failure(request, prompt_hash, "LOW_CONFIDENCE")
        return AiAssessment(
            decision=parsed.decision,
            confidence=parsed.confidence,
            reason_codes=parsed.reason_codes,
            rationale=parsed.rationale,
            memory_refs=parsed.memory_refs,
            prompt_hash=prompt_hash,
            model=self.model,
        )

    def _safe_failure(
        self,
        request: DecisionRequest,
        prompt_hash: str,
        reason: str,
    ) -> AiAssessment:
        decision = (
            AiDecision.REJECT_ENTRY
            if request.candidate is CandidateAction.ENTRY_CANDIDATE
            else AiDecision.HOLD
        )
        return AiAssessment(
            decision=decision,
            confidence=0,
            reason_codes=(reason,),
            rationale="AI decision unavailable; deterministic safe action applied.",
            memory_refs=(),
            prompt_hash=prompt_hash,
            model=self.model,
        )
