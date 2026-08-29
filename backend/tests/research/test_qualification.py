from __future__ import annotations

from dataclasses import dataclass

from goldguard.research.qualification import QualificationService


@dataclass
class EvidenceMock:
    trades: int


def test_first_live_requires_full_paper_floor() -> None:
    service = QualificationService()
    report_bad = service.evaluate(EvidenceMock(trades=199))
    assert report_bad.qualified is False
    assert "MIN_200_PAPER_TRADES" in report_bad.failures

    report_good = service.evaluate(EvidenceMock(trades=205))
    assert report_good.qualified is True
    assert len(report_good.failures) == 0

