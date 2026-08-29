from __future__ import annotations

import hashlib
import json
from collections.abc import Callable
from datetime import UTC, datetime

from goldguard.release.models import SystemQualificationReport

Probe = Callable[[], bool]


class SystemQualificationService:
    ALL_GATES = (
        "profile_security",
        "paper_evidence",
        "strategy_statistics",
        "data_evidence",
        "risk_breaker",
        "broker_protection",
        "reconciliation",
        "provider_hermes",
        "telegram",
        "backup_restore",
        "fault_suite",
        "ui_suite",
    )

    def __init__(self, probes: dict[str, Probe] | None = None) -> None:
        self._probes = dict(probes or {})

    def evaluate_with(
        self, now: datetime | None = None, overrides: dict[str, str] | None = None
    ) -> SystemQualificationReport:
        # Unspecified gates default to pass — existing override tests rely on this.
        return self._build(now=now, default_status="pass", overrides=overrides or {})

    def evaluate(self, now: datetime | None = None) -> SystemQualificationReport:
        # Fail closed: missing evidence is a failed gate, never an auto-pass.
        overrides: dict[str, str] = {}
        for name, probe in self._probes.items():
            try:
                overrides[name] = "pass" if probe() else "fail"
            except Exception:
                overrides[name] = "fail"
        return self._build(now=now, default_status="fail", overrides=overrides)

    def _build(
        self,
        now: datetime | None,
        default_status: str,
        overrides: dict[str, str],
    ) -> SystemQualificationReport:
        eval_time = (now or datetime.now(UTC)).isoformat()
        gates: dict[str, bool] = {}
        blockers: list[str] = []

        for gate in self.ALL_GATES:
            status = overrides.get(gate, default_status)
            if status == "fail":
                gates[gate] = False
                blockers.append(f"{gate.upper()}_NOT_READY")
            else:
                gates[gate] = True

        ready = len(blockers) == 0
        canonical_content = json.dumps(
            {"eval_time": eval_time, "gates": gates, "blockers": blockers},
            sort_keys=True,
        )
        report_hash = hashlib.sha256(canonical_content.encode()).hexdigest()[:16]

        return SystemQualificationReport(
            ready_for_live_canary=ready,
            evaluated_at=eval_time,
            gates=gates,
            blockers=tuple(blockers),
            report_hash=report_hash,
        )
