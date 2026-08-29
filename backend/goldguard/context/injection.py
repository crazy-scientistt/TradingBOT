from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import ClassVar


@dataclass(frozen=True, slots=True)
class InjectionAssessment:
    flagged: bool
    score: float
    reasons: list[str] = field(default_factory=list)


class InjectionScanner:
    PATTERNS: ClassVar[list[re.Pattern[str]]] = [
        re.compile(r"ignore\s+(previous|prior|all)\s+instructions?", re.IGNORECASE),
        re.compile(r"ignore\s+risk\s+limits?", re.IGNORECASE),
        re.compile(r"call\s+the\s+broker", re.IGNORECASE),
        re.compile(r"system\s*prompt", re.IGNORECASE),
        re.compile(r"disregard\s+safety", re.IGNORECASE),
        re.compile(r"execute\s+order\s+now", re.IGNORECASE),
    ]

    def scan(self, text: str) -> InjectionAssessment:
        reasons: list[str] = []
        for pat in self.PATTERNS:
            if pat.search(text):
                reasons.append(f"matched_pattern_{pat.pattern}")

        flagged = len(reasons) > 0
        score = 1.0 if flagged else 0.0
        return InjectionAssessment(flagged=flagged, score=score, reasons=reasons)

