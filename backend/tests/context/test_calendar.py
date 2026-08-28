from datetime import UTC, datetime, timedelta

from goldguard.context.calendar import parse_events


def test_high_impact_usd_event_is_blackout() -> None:
    now = datetime(2026, 8, 28, 12, 0, tzinfo=UTC)
    events = parse_events(
        [
            {
                "title": "CPI m/m",
                "country": "USD",
                "impact": "High",
                "date": (now + timedelta(minutes=20)).isoformat(),
            },
            {
                "title": "German CPI",
                "country": "EUR",
                "impact": "High",
                "date": now.isoformat(),
            },
        ]
    )
    from goldguard.context.calendar import EconomicCalendar

    calendar = EconomicCalendar()
    calendar.events = events
    flagged, active = calendar.is_blackout(now)
    assert flagged is True
    assert active is not None
    assert active.title == "CPI m/m"


def test_quiet_window_is_not_blackout() -> None:
    now = datetime(2026, 8, 28, 12, 0, tzinfo=UTC)
    events = parse_events(
        [
            {
                "title": "CPI m/m",
                "country": "USD",
                "impact": "High",
                "date": (now + timedelta(hours=5)).isoformat(),
            }
        ]
    )
    from goldguard.context.calendar import EconomicCalendar

    calendar = EconomicCalendar()
    calendar.events = events
    flagged, active = calendar.is_blackout(now)
    assert flagged is False
    assert active is None
