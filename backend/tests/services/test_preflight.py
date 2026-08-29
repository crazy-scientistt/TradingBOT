from __future__ import annotations

from goldguard.domain.profile import default_autonomous_profile
from goldguard.services.preflight import PreflightService


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


def test_preflight_report_with_failure() -> None:
    profile = default_autonomous_profile()
    report = PreflightService().evaluate(profile)
    failed = report.with_failure("paper_qualification", detail="needs 200 paper trades")
    assert failed.ready is False
    assert failed.has_failure("paper_qualification")

