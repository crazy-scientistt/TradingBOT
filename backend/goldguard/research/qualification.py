from __future__ import annotations

from dataclasses import dataclass
from typing import Any


class InvalidGenomeTransition(Exception):
    pass


@dataclass(frozen=True, slots=True)
class QualificationReport:
    qualified: bool
    failures: tuple[str, ...]
    details: dict[str, Any]


class QualificationService:
    def evaluate(self, evidence_data: Any) -> QualificationReport:
        trades = getattr(evidence_data, "trades", 0)
        failures: list[str] = []

        if trades < 200:
            failures.append("MIN_200_PAPER_TRADES")

        return QualificationReport(
            qualified=len(failures) == 0,
            failures=tuple(failures),
            details={"trades": trades},
        )

