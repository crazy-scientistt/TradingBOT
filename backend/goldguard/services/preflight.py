from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass

from goldguard.domain.profile import AutonomousProfile


@dataclass(frozen=True, slots=True)
class PreflightCheck:
    id: str
    label: str
    status: str  # "pass", "fail", "warn"
    detail: str


@dataclass(frozen=True, slots=True)
class PreflightReport:
    ready: bool
    checks: tuple[PreflightCheck, ...]

    def with_failure(self, failed_id: str, detail: str = "check failed") -> PreflightReport:
        updated = [
            (
                PreflightCheck(
                    id=c.id,
                    label=c.label,
                    status="fail" if c.id == failed_id else c.status,
                    detail=detail if c.id == failed_id else c.detail,
                )
                if c.id == failed_id
                else c
            )
            for c in self.checks
        ]
        if not any(c.id == failed_id for c in self.checks):
            updated.append(
                PreflightCheck(
                    id=failed_id,
                    label=failed_id.replace("_", " ").title(),
                    status="fail",
                    detail=detail,
                )
            )
        return PreflightReport(ready=False, checks=tuple(updated))

    def has_failure(self, check_id: str) -> bool:
        return any(c.id == check_id and c.status == "fail" for c in self.checks)


PreflightProbe = Callable[[AutonomousProfile], PreflightCheck]


class PreflightService:
    GATE_DEFINITIONS = (
        (
            "paper_qualification",
            "Paper Qualification Gate",
            "verified 200+ paper trades with positive expectancy",
        ),
        (
            "binance_permissions",
            "Binance API Key Permissions",
            "read and spot/futures trade enabled",
        ),
        (
            "withdrawals_disabled",
            "Withdrawals Safety",
            "withdrawal permissions confirmed disabled",
        ),
        (
            "market_freshness",
            "Market Data Freshness",
            "real-time exchange candle and quote streams active",
        ),
        (
            "database_integrity",
            "Database Integrity",
            "durable sqlite wal and migration integrity verified",
        ),
        (
            "opencodex_route",
            "OpenCodex Provider Route",
            "antigravity ai model route verified and responsive",
        ),
        (
            "hermes_route",
            "Hermes Agent Route",
            "hermes research and memory loop service active",
        ),
        (
            "telegram_critical",
            "Telegram Notification Bridge",
            "telegram token configured for critical alerts",
        ),
        (
            "reconciliation",
            "Exchange Reconciliation",
            "zero discrepancy between local ledger and exchange state",
        ),
    )

    def __init__(self, probes: Mapping[str, PreflightProbe] | None = None) -> None:
        self._probes = dict(probes or {})

    def evaluate(self, profile: AutonomousProfile) -> PreflightReport:
        checks: list[PreflightCheck] = []

        for gate_id, label, _detail in self.GATE_DEFINITIONS:
            probe = self._probes.get(gate_id)
            if probe is None:
                checks.append(
                    PreflightCheck(
                        id=gate_id,
                        label=label,
                        status="fail",
                        detail="runtime observation is not configured; Live remains blocked",
                    )
                )
                continue
            try:
                check = probe(profile)
            except Exception:
                check = PreflightCheck(
                    id=gate_id,
                    label=label,
                    status="fail",
                    detail="runtime observation failed; Live remains blocked",
                )
            if check.id != gate_id or check.status not in {"pass", "warn", "fail"}:
                check = PreflightCheck(
                    id=gate_id,
                    label=label,
                    status="fail",
                    detail="runtime observation was invalid; Live remains blocked",
                )
            checks.append(check)

        return PreflightReport(
            ready=all(check.status == "pass" for check in checks),
            checks=tuple(checks),
        )
