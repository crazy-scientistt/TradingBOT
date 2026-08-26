import hashlib
import json
from dataclasses import asdict

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from goldguard.ai.gemini import (
    KNOWN_REASON_CODES,
    AiAssessment,
    DecisionRequest,
)
from goldguard.ai.prompts import DECISION_SYSTEM_PROMPT
from goldguard.domain.enums import AiDecision, CandidateAction
from goldguard.domain.models import ai_decision_is_compatible
from goldguard.providers.client import GatewayClient, GatewayError
from goldguard.providers.models import ChatCompletionRequest, ChatMessage
from goldguard.providers.service import RouteService


class _DecisionResponseSchema(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    decision: AiDecision
    confidence: int = Field(ge=0, le=100)
    reason_codes: tuple[str, ...] = Field(max_length=8)
    rationale: str = Field(min_length=1, max_length=500)
    memory_refs: tuple[str, ...] = Field(default_factory=tuple, max_length=3)


class DecisionVetoEngine:
    """Multi-provider AI Decision Veto Engine with strict schema validation."""

    def __init__(
        self,
        *,
        route_service: RouteService,
        gateway_client: GatewayClient,
        minimum_confidence: int = 70,
    ) -> None:
        self.route_service = route_service
        self.gateway_client = gateway_client
        self.minimum_confidence = minimum_confidence

    async def decide(self, request: DecisionRequest) -> AiAssessment:
        routes = self.route_service.get_active_routes()
        route = routes.get("decision")
        model = route.model if route else "google-antigravity/gemini-3.7-flash"

        prompt_material = json.dumps(
            asdict(request),
            sort_keys=True,
            default=str,
            separators=(",", ":"),
        )
        prompt_hash = hashlib.sha256(prompt_material.encode()).hexdigest()

        chat_request = ChatCompletionRequest(
            model=model,
            messages=[
                ChatMessage(role="system", content=DECISION_SYSTEM_PROMPT),
                ChatMessage(
                    role="user",
                    content=(
                        "Evaluate the following candidate decision under the strict schema.\n"
                        f"{prompt_material}"
                    ),
                ),
            ],
            temperature=0.0,
            response_format={"type": "json_object"},
            reasoning_effort="high",
        )

        try:
            resp = await self.gateway_client.chat_completion(chat_request)
            raw_text = resp.content
            parsed = _DecisionResponseSchema.model_validate_json(raw_text)
        except (GatewayError, ValidationError, json.JSONDecodeError, Exception):
            return self._safe_failure(request, prompt_hash, model, "INVALID_AI_RESPONSE")

        if any(code not in KNOWN_REASON_CODES for code in parsed.reason_codes):
            return self._safe_failure(request, prompt_hash, model, "INVALID_AI_RESPONSE")

        if not ai_decision_is_compatible(request.candidate, parsed.decision):
            return self._safe_failure(request, prompt_hash, model, "INCOMPATIBLE_AI_DECISION")

        if (
            parsed.decision is AiDecision.APPROVE_ENTRY
            and parsed.confidence < self.minimum_confidence
        ):
            return self._safe_failure(request, prompt_hash, model, "LOW_CONFIDENCE")

        return AiAssessment(
            decision=parsed.decision,
            confidence=parsed.confidence,
            reason_codes=parsed.reason_codes,
            rationale=parsed.rationale,
            memory_refs=parsed.memory_refs,
            prompt_hash=prompt_hash,
            model=model,
        )

    def _safe_failure(
        self,
        request: DecisionRequest,
        prompt_hash: str,
        model: str,
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
            rationale="AI decision failed or rejected; deterministic safety fallback applied.",
            memory_refs=(),
            prompt_hash=prompt_hash,
            model=model,
        )
