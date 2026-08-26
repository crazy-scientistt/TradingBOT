import hashlib
import json
from dataclasses import asdict, dataclass
from decimal import Decimal
from typing import Literal


@dataclass(frozen=True)
class TradeOutcome:
    trade_id: str
    namespace: Literal["historical", "forward"]
    hypothesis: str
    realized_pnl: Decimal
    maximum_adverse_excursion: Decimal
    maximum_favorable_excursion: Decimal
    fees: Decimal
    exit_reason: str
    regime_tags: tuple[str, ...]
    context_error: bool
    rule_adherent: bool


@dataclass(frozen=True)
class Reflection:
    identifier: str
    trade_id: str
    namespace: Literal["historical", "forward"]
    hypothesis: str
    net_pnl: Decimal
    fee_drag: Decimal
    maximum_adverse_excursion: Decimal
    maximum_favorable_excursion: Decimal
    exit_reason: str
    regime_tags: tuple[str, ...]
    lesson_code: str
    lesson: str


class ReflectionEngine:
    def create(self, outcome: TradeOutcome) -> Reflection:
        if not outcome.rule_adherent:
            lesson_code = "PROCESS_VIOLATION"
            lesson = "Process discipline failed; exclude this outcome from setup tuning."
        elif outcome.context_error:
            lesson_code = "CONTEXT_MISS"
            lesson = "The cited context assessment missed a material adverse driver."
        elif outcome.realized_pnl > 0:
            lesson_code = "VALID_SETUP_WIN"
            lesson = "The planned setup completed profitably without breaking risk rules."
        else:
            lesson_code = "VALID_SETUP_LOSS"
            lesson = "A rule-compliant loss; review regime and context without increasing risk."
        material = json.dumps(asdict(outcome), sort_keys=True, default=str, separators=(",", ":"))
        identifier = hashlib.sha256(material.encode()).hexdigest()
        return Reflection(
            identifier=identifier,
            trade_id=outcome.trade_id,
            namespace=outcome.namespace,
            hypothesis=outcome.hypothesis,
            net_pnl=outcome.realized_pnl,
            fee_drag=outcome.fees,
            maximum_adverse_excursion=outcome.maximum_adverse_excursion,
            maximum_favorable_excursion=outcome.maximum_favorable_excursion,
            exit_reason=outcome.exit_reason,
            regime_tags=outcome.regime_tags,
            lesson_code=lesson_code,
            lesson=lesson,
        )


class ReflectionStore:
    def __init__(self) -> None:
        self._items: list[Reflection] = []

    def add(self, reflection: Reflection) -> None:
        if any(item.identifier == reflection.identifier for item in self._items):
            return
        self._items.append(reflection)

    def relevant(
        self,
        *,
        namespace: Literal["historical", "forward"],
        regime_tags: tuple[str, ...],
        limit: int = 3,
    ) -> tuple[Reflection, ...]:
        if limit < 1 or limit > 3:
            raise ValueError("reflection retrieval limit must be from one through three")
        wanted = set(regime_tags)
        matches = [
            item
            for item in self._items
            if item.namespace == namespace and wanted.issubset(item.regime_tags)
        ]
        return tuple(matches[-limit:])
