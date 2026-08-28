"""High-impact USD event calendar. Fail-open if the feed is down; fail-closed when an event is near."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx

logger = logging.getLogger("goldguard.calendar")

FF_CALENDAR_URL = "https://nfs.faireconomy.media/ff_calendar_thisweek.json"
HIGH_IMPACT_LABELS = frozenset({"high", "red"})
HIGH_KEYWORDS = (
    "cpi",
    "fomc",
    "non-farm",
    "nonfarm",
    "nfp",
    "interest rate",
    "fed",
    "pce",
    "unemployment",
    "payroll",
    "gdp",
)
USD_COUNTRIES = frozenset({"usd", "united states", "usa", "us"})
BLACKOUT_BEFORE = timedelta(hours=1)
BLACKOUT_AFTER = timedelta(minutes=30)


@dataclass(frozen=True)
class CalendarEvent:
    title: str
    country: str
    impact: str
    when: datetime
    forecast: str | None
    previous: str | None

    @property
    def high_impact_usd(self) -> bool:
        country = self.country.lower()
        impact = self.impact.lower()
        title = self.title.lower()
        if country not in USD_COUNTRIES:
            return False
        if impact in HIGH_IMPACT_LABELS:
            return True
        return any(keyword in title for keyword in HIGH_KEYWORDS)


def _parse_when(raw: object) -> datetime | None:
    if isinstance(raw, (int, float)):
        value = float(raw)
        if value > 10_000_000_000:
            value /= 1000
        return datetime.fromtimestamp(value, tz=UTC)
    if not isinstance(raw, str) or not raw.strip():
        return None
    text = raw.strip()
    for fmt in (
        "%Y-%m-%dT%H:%M:%S%z",
        "%Y-%m-%dT%H:%M:%S.%f%z",
        "%Y-%m-%dT%H:%M:%SZ",
        "%Y-%m-%d %H:%M:%S",
        "%b %d, %Y %I:%M%p",
        "%b %d %Y %H:%M",
    ):
        try:
            parsed = datetime.strptime(text.replace("Z", "+0000") if fmt.endswith("%z") else text, fmt)
            return parsed.replace(tzinfo=UTC) if parsed.tzinfo is None else parsed.astimezone(UTC)
        except ValueError:
            continue
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
        return parsed.replace(tzinfo=UTC) if parsed.tzinfo is None else parsed.astimezone(UTC)
    except ValueError:
        return None


def parse_events(payload: object) -> list[CalendarEvent]:
    rows = payload if isinstance(payload, list) else []
    events: list[CalendarEvent] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        when = _parse_when(row.get("date") or row.get("datetime") or row.get("time"))
        if when is None:
            continue
        events.append(
            CalendarEvent(
                title=str(row.get("title") or row.get("event") or "Untitled"),
                country=str(row.get("country") or row.get("currency") or ""),
                impact=str(row.get("impact") or row.get("volatility") or ""),
                when=when,
                forecast=None if row.get("forecast") in (None, "") else str(row.get("forecast")),
                previous=None if row.get("previous") in (None, "") else str(row.get("previous")),
            )
        )
    events.sort(key=lambda item: item.when)
    return events


class EconomicCalendar:
    def __init__(self, *, http_client: httpx.AsyncClient | None = None) -> None:
        self._client = http_client
        self._owned = http_client is None
        self.events: list[CalendarEvent] = []
        self.source = "unconfigured"
        self.updated_at: datetime | None = None
        self.detail: str | None = "calendar has not been fetched yet"

    def is_blackout(self, now: datetime) -> tuple[bool, CalendarEvent | None]:
        current = now.astimezone(UTC)
        for event in self.events:
            if not event.high_impact_usd:
                continue
            start = event.when - BLACKOUT_BEFORE
            end = event.when + BLACKOUT_AFTER
            if start <= current <= end:
                return True, event
        return False, None

    def upcoming(self, *, limit: int = 12) -> list[CalendarEvent]:
        now = datetime.now(UTC)
        future = [event for event in self.events if event.when >= now - BLACKOUT_AFTER]
        return future[:limit]

    def as_context_rows(self) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        now = datetime.now(UTC)
        blackout, active = self.is_blackout(now)
        for event in self.upcoming():
            rows.append(
                {
                    "id": f"{event.when.isoformat()}-{event.title}",
                    "category": "fed" if "fed" in event.title.lower() or "fomc" in event.title.lower() else "yields",
                    "title": (
                        f"{'[BLACKOUT] ' if blackout and active and event.title == active.title else ''}"
                        f"{event.title} ({event.country} {event.impact})"
                    ),
                    "direction": "neutral",
                    "severity": "high" if event.high_impact_usd else "medium",
                    "contradictory": False,
                    "source": FF_CALENDAR_URL,
                    "time": event.when.strftime("%H:%M"),
                    "when": event.when.isoformat(),
                }
            )
        return rows

    async def refresh(self) -> None:
        client = self._client or httpx.AsyncClient(timeout=15.0)
        try:
            response = await client.get(FF_CALENDAR_URL)
            response.raise_for_status()
            self.events = parse_events(response.json())
            self.source = "forexfactory-calendar"
            self.updated_at = datetime.now(UTC)
            self.detail = None
        except Exception as exc:
            logger.warning("Economic calendar refresh failed: %s", exc)
            self.detail = f"calendar unavailable: {exc}"
            if not self.events:
                self.source = "unavailable"
        finally:
            if self._owned and self._client is None:
                await client.aclose()
