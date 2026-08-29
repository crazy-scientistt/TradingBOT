from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True, slots=True)
class QualificationGateResult:
    name: str
    passed: bool
    details: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class SystemQualificationReport:
    ready_for_live_canary: bool
    evaluated_at: str
    gates: dict[str, bool]
    blockers: tuple[str, ...]
    report_hash: str

