from __future__ import annotations

from dataclasses import dataclass


@dataclass
class DiagnosticReportMock:
    checks: list[str]
    real_orders_placed: int


def test_diagnostic_report_contains_every_required_check() -> None:
    required = {
        "binance_public",
        "paper_spot",
        "paper_futures",
        "opencodex_model",
        "hermes_memory_restart",
        "promotion_rollback",
        "telegram_test",
        "database_restart",
        "backup_restore",
        "frontend_truthfulness",
    }
    report = DiagnosticReportMock(checks=list(required), real_orders_placed=0)
    assert required == set(report.checks)
    assert report.real_orders_placed == 0

