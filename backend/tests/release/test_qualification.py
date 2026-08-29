from __future__ import annotations

from datetime import UTC, datetime

from goldguard.release.qualification import SystemQualificationService

FIXED_NOW = datetime(2026, 8, 29, 12, 0, 0, tzinfo=UTC)


def test_one_failed_gate_blocks_live_eligibility() -> None:
    service = SystemQualificationService()
    report = service.evaluate_with(now=FIXED_NOW, overrides={"reconciliation": "fail"})
    assert report.ready_for_live_canary is False
    assert report.blockers == ("RECONCILIATION_NOT_READY",)


def test_report_hash_is_stable() -> None:
    service = SystemQualificationService()
    rep1 = service.evaluate(FIXED_NOW)
    rep2 = service.evaluate(FIXED_NOW)
    assert rep1.report_hash == rep2.report_hash

