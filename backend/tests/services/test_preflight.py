from __future__ import annotations

from goldguard.domain.profile import default_autonomous_profile
from goldguard.services.preflight import PreflightCheck, PreflightService


def test_preflight_service_evaluates_all_gates() -> None:
    profile = default_autonomous_profile()
    service = PreflightService()
    report = service.evaluate(profile)

    assert len(report.checks) == 9
    gate_ids = {c.id for c in report.checks}
    assert gate_ids == {
        "paper_qualification",
        "binance_permissions",
        "withdrawals_disabled",
        "market_freshness",
        "database_integrity",
        "opencodex_route",
        "hermes_route",
        "telegram_critical",
        "reconciliation",
    }
    assert report.ready is False
    assert all(check.status == "fail" for check in report.checks)


def test_preflight_passes_only_with_explicit_runtime_observations() -> None:
    probes = {
        gate_id: (
            lambda _profile, gate_id=gate_id, label=label: PreflightCheck(
                id=gate_id,
                label=label,
                status="pass",
                detail="verified by test runtime",
            )
        )
        for gate_id, label, _ in PreflightService.GATE_DEFINITIONS
    }

    report = PreflightService(probes=probes).evaluate(default_autonomous_profile())

    assert report.ready is True
    assert all(check.status == "pass" for check in report.checks)


def test_preflight_report_with_failure() -> None:
    profile = default_autonomous_profile()
    report = PreflightService().evaluate(profile)
    failed = report.with_failure("paper_qualification", detail="needs 200 paper trades")
    assert failed.ready is False
    assert failed.has_failure("paper_qualification")
