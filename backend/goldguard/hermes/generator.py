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
    model_config = ConfigDict(extra="ignore", frozen=True)

    hypothesis: str = Field(default="", max_length=1000)
    evidence_refs: list[str] = Field(default_factory=list)
    parameter_changes: dict[str, str] = Field(min_length=1, max_length=10)
    rationale: str = Field(default="", max_length=1000)
    evidence_ids: list[str] = Field(default_factory=list)

    def resolved_hypothesis(self) -> str:
        text = (self.hypothesis or self.rationale).strip()
        if len(text) >= 10:
            return text[:1000]
        return "Hermes bounded parameter mutation from live market evidence."

    def resolved_evidence(self) -> list[str]:
        refs = [item for item in (self.evidence_refs or self.evidence_ids) if item]
        return refs or ["live-market"]

    @classmethod
    def coerce(cls, raw: dict[str, Any]) -> "_RawProposalResponse":
        changes = raw.get("parameter_changes") or {}
        if isinstance(changes, dict):
            raw = {
                **raw,
                "parameter_changes": {str(key): str(value) for key, value in changes.items()},
            }
        return cls.model_validate(raw)


HERMES_SYSTEM_PROMPT = """You are Hermes, the autonomous quantitative researcher for GoldGuard.
Propose strictly bounded parameter modifications to the baseline StrategyGenome.

Rules:
1. Change 1 or 2 parameters. Never return an empty parameter_changes object.
2. Every parameter must stay strictly within its defined safe bounds.
3. Include a scientific hypothesis (min 20 chars) and evidence refs.
4. Output strictly valid JSON, no markdown.
5. Protective bounds: do not increase stop_atr_multiple above the parent,
   and do not decrease reward_r_multiple below the parent. Tightening is allowed.

Allowed parameter_changes keys:
rsi_recovery, rsi_ceiling, minimum_volume_ratio, stop_atr_multiple,
reward_r_multiple, minimum_atr_rate, maximum_atr_rate

Example:
{
  "hypothesis": "A slightly higher RSI recovery reduces chop entries in a rising 1h trend.",
  "evidence_refs": ["live-market"],
  "parameter_changes": {"rsi_recovery": "48"},
  "rationale": "Fewer false starts after shallow pullbacks."
}
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
                f"{HERMES_SYSTEM_PROMPT}\nPropose strategy refinement:\n{prompt_content}"
            )
        except HermesUnavailable as exc:
            raise ProposalValidationError("HERMES_UNAVAILABLE") from exc
        parsed = self._parse_proposal(content)
        if parsed is None or not parsed.parameter_changes:
            try:
                content = await self.hermes_client.complete(
                    "Your previous JSON had empty or invalid parameter_changes. "
                    "Return JSON with 1 or 2 keys from rsi_recovery, rsi_ceiling, "
                    "minimum_volume_ratio, stop_atr_multiple, reward_r_multiple, "
                    "minimum_atr_rate, maximum_atr_rate. Values must be decimal strings "
                    "inside the supplied bounds.\n"
                    f"{prompt_content}"
                )
            except HermesUnavailable as exc:
                raise ProposalValidationError("HERMES_UNAVAILABLE") from exc
            parsed = self._parse_proposal(content)
        if parsed is None:
            raise ProposalValidationError("Malformed LLM proposal response: unparseable JSON")
        if not parsed.parameter_changes:
            raise ProposalValidationError(
                "Malformed LLM proposal response: parameter_changes must contain 1-2 items"
            )

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
            "atr_stop_multiple": "stop_atr_multiple",
            "stop_loss": "stop_atr_multiple",
            "r_multiple": "reward_r_multiple",
            "take_profit": "reward_r_multiple",
            "volume_ratio": "minimum_volume_ratio",
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
                if (
                    isinstance(cond.left, IndicatorSpec)
                    and cond.left.indicator == "rsi"
                    and cond.op in ("gte", "gt")
                    and cond.left.offset == 0
                ):
                    new_entry[i] = Condition(
                        left=cond.left,
                        op=cond.op,
                        right=new_rsi,
                    )

        if "rsi_ceiling" in validated_changes:
            new_ceil = validated_changes["rsi_ceiling"]
            for i, cond in enumerate(new_entry):
                if (
                    isinstance(cond.left, IndicatorSpec)
                    and cond.left.indicator == "rsi"
                    and cond.op in ("lt", "lte")
                    and cond.left.offset == 0
                ):
                    new_entry[i] = Condition(
                        left=cond.left,
                        op=cond.op,
                        right=new_ceil,
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

        new_exit = parent_genome.exit
        exit_updates: dict[str, Decimal] = {}
        if "stop_atr_multiple" in validated_changes:
            exit_updates["stop_atr_multiple"] = validated_changes["stop_atr_multiple"]
        if "reward_r_multiple" in validated_changes:
            exit_updates["r_multiple_min"] = validated_changes["reward_r_multiple"]
        if exit_updates:
            new_exit = parent_genome.exit.model_copy(update=exit_updates)

        hypothesis = parsed.resolved_hypothesis()
        evidence = parsed.resolved_evidence()
        new_genome_id = f"hermes-{uuid4().hex[:8]}"
        return StrategyGenome(
            genome_id=new_genome_id,
            parent_id=parent_genome.genome_id,
            title=f"Refinement: {hypothesis[:50]}",
            hypothesis=hypothesis,
            evidence_refs=tuple(evidence),
            regime=parent_genome.regime,
            guard=new_guard,
            entry=tuple(new_entry),
            exit=new_exit,
        )

    @staticmethod
    def _parse_proposal(content: str) -> _RawProposalResponse | None:
        match = content.find("{")
        end = content.rfind("}")
        payload = content[match : end + 1] if match >= 0 and end > match else content
        try:
            return _RawProposalResponse.coerce(json.loads(payload))
        except (ValidationError, json.JSONDecodeError, TypeError, ValueError):
            return None
