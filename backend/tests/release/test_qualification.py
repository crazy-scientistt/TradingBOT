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


def test_evaluate_without_overrides_is_not_live_ready() -> None:
    service = SystemQualificationService()
    report = service.evaluate(FIXED_NOW)
    assert report.ready_for_live_canary is False
    assert "PAPER_EVIDENCE_NOT_READY" in report.blockers
    assert report.gates["paper_evidence"] is False


def test_probe_can_pass_one_gate_without_auto_passing_the_rest() -> None:
    service = SystemQualificationService(probes={"telegram": lambda: True})
    report = service.evaluate(FIXED_NOW)
    assert report.gates["telegram"] is True
    assert report.gates["paper_evidence"] is False
    assert report.ready_for_live_canary is False


def test_failing_probe_stays_failed() -> None:
    service = SystemQualificationService(probes={"backup_restore": lambda: False})
    report = service.evaluate(FIXED_NOW)
    assert report.gates["backup_restore"] is False
    assert "BACKUP_RESTORE_NOT_READY" in report.blockers
