import json
from collections.abc import Sequence
from decimal import Decimal
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from goldguard.domain.defaults import PARAMETER_BOUNDS
from goldguard.hermes.client import HermesClient, HermesUnavailable
from goldguard.providers.client import GatewayClient
from goldguard.strategy.genome import (
    Condition,
    GuardBounds,
    IndicatorSpec,
    StrategyGenome,
)


class ProposalValidationError(ValueError):
    pass


class _RawProposalResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    hypothesis: str = Field(min_length=10, max_length=1000)
    evidence_refs: list[str] = Field(min_length=1, max_length=10)
    parameter_changes: dict[str, str] = Field(min_length=1, max_length=10)


HERMES_SYSTEM_PROMPT = """You are Hermes, the autonomous quantitative researcher for GoldGuard.
Your task is to analyze recent trade post-mortems (reflections) and propose
strictly bounded parameter modifications to the baseline StrategyGenome.

Rules:
1. Propose AT MOST 2 parameter changes per generation.
2. Every parameter must stay strictly within its defined safe bounds.
3. Every proposal must include a rigorous scientific hypothesis and cite specific evidence IDs.
4. Output strictly valid JSON matching the schema.
"""


class StrategyProposalGenerator:
    """Hermes is the sole proposal owner. No silent OpenCodex fallback."""

    def __init__(
        self,
        gateway_client: GatewayClient | None = None,
        model: str = "google-antigravity/gemini-3.7-flash",
        hermes_client: HermesClient | None = None,
    ) -> None:
        self.gateway_client = gateway_client
        self.model = model
        self.hermes_client = hermes_client

    async def propose(
        self,
        *,
        parent_genome: StrategyGenome,
        reflections: Sequence[dict[str, Any]],
        market_summary: str,
    ) -> StrategyGenome:
        if self.hermes_client is None:
            raise ProposalValidationError("HERMES_UNAVAILABLE")
        bounds_summary = {k: [str(b[0]), str(b[1])] for k, b in PARAMETER_BOUNDS.items()}
        prompt_content = json.dumps(
            {
                "parent_genome_id": parent_genome.genome_id,
                "parameter_bounds": bounds_summary,
                "reflections": list(reflections),
                "market_summary": market_summary,
            },
            indent=2,
        )
        try:
            content = await self.hermes_client.complete(
                f"Propose strategy refinement:\n{prompt_content}"
            )
        except HermesUnavailable as exc:
            raise ProposalValidationError("HERMES_UNAVAILABLE") from exc
        match = content.find("{")
        end = content.rfind("}")
        payload = content[match : end + 1] if match >= 0 and end > match else content
        try:
            parsed = _RawProposalResponse.model_validate_json(payload)
        except (ValidationError, Exception) as exc:
            raise ProposalValidationError(f"Malformed LLM proposal response: {exc}") from exc

        # Validate max 2 parameter changes
        if len(parsed.parameter_changes) > 2:
            raise ProposalValidationError(
                f"Proposal exceeds maximum of 2 parameter changes "
                f"(found {len(parsed.parameter_changes)})"
            )

        # Validate parameter bounds
        validated_changes: dict[str, Decimal] = {}
        aliases = {
            "rsi_entry_recovery": "rsi_recovery",
            "min_atr_rate": "minimum_atr_rate",
            "max_atr_rate": "maximum_atr_rate",
        }
        for param_str, val_str in parsed.parameter_changes.items():
            param_str = aliases.get(param_str, param_str)
            if param_str not in PARAMETER_BOUNDS:
                raise ProposalValidationError(f"Unknown parameter: {param_str}")
            try:
                dec_val = Decimal(val_str)
            except Exception as exc:
                raise ProposalValidationError(
                    f"Invalid decimal value for {param_str}: {val_str}"
                ) from exc

            min_val, max_val = PARAMETER_BOUNDS[param_str]
            if not (min_val <= dec_val <= max_val):
                raise ProposalValidationError(
                    f"Parameter {param_str} value {dec_val} is outside safe "
                    f"parameter bounds [{min_val}, {max_val}]"
                )
            validated_changes[param_str] = dec_val

        # Apply mutations to clone of parent_genome
        new_guard = parent_genome.guard
        new_entry = list(parent_genome.entry)

        if "minimum_volume_ratio" in validated_changes:
            new_vol = validated_changes["minimum_volume_ratio"]
            for i, cond in enumerate(new_entry):
                if isinstance(cond.left, IndicatorSpec) and cond.left.indicator == "volume_ratio":
                    new_entry[i] = Condition(
                        left=cond.left,
                        op=cond.op,
                        right=new_vol,
                    )

        if "rsi_recovery" in validated_changes:
            new_rsi = validated_changes["rsi_recovery"]
            for i, cond in enumerate(new_entry):
                if isinstance(cond.left, IndicatorSpec) and cond.left.indicator == "rsi":
                    new_entry[i] = Condition(
                        left=cond.left,
                        op=cond.op,
                        right=new_rsi,
                    )

        if "minimum_atr_rate" in validated_changes or "maximum_atr_rate" in validated_changes:
            new_guard = GuardBounds(
                min_atr_rate=validated_changes.get(
                    "minimum_atr_rate", parent_genome.guard.min_atr_rate
                ),
                max_atr_rate=validated_changes.get(
                    "maximum_atr_rate", parent_genome.guard.max_atr_rate
                ),
                max_spread_rate=parent_genome.guard.max_spread_rate,
            )

        new_genome_id = f"hermes-{uuid4().hex[:8]}"
        return StrategyGenome(
            genome_id=new_genome_id,
            parent_id=parent_genome.genome_id,
            title=f"Refinement: {parsed.hypothesis[:50]}",
            hypothesis=parsed.hypothesis,
            evidence_refs=tuple(parsed.evidence_refs),
            regime=parent_genome.regime,
            guard=new_guard,
            entry=tuple(new_entry),
            exit=parent_genome.exit,
        )
