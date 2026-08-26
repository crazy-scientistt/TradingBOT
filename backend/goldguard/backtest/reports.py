from dataclasses import fields
from decimal import Decimal

from goldguard.backtest.metrics import PerformanceReport


def report_to_dict(report: PerformanceReport) -> dict[str, bool | int | str | None]:
    """Return an exact, JSON-safe report without converting money to floats."""
    result: dict[str, bool | int | str | None] = {}
    for field in fields(report):
        value = getattr(report, field.name)
        result[field.name] = str(value) if isinstance(value, Decimal) else value
    return result
