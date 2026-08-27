import sqlite3
from datetime import UTC, datetime, timedelta

import pytest
from goldguard.observability.events import AgentEvent, EventBus
from goldguard.storage.database import Database
from goldguard.storage.repositories import AgentEventRepository


def test_recent_is_bounded_and_expires_routine_events() -> None:
    bus = EventBus(max_events=100, routine_ttl=timedelta(seconds=1))
    old = AgentEvent.create("routine", "old", (), {})
    object.__setattr__(old, "occurred_at", datetime.now(UTC) - timedelta(seconds=5))
    bus.publish(old)
    for index in range(40):
        bus.publish(AgentEvent.create("routine", str(index), (), {"index": index}))

    recent = bus.recent(30)
    assert len(recent) == 30
    assert old not in recent


def test_recent_hard_caps_display_limit_at_thirty() -> None:
    bus = EventBus(max_events=100)
    for index in range(50):
        bus.publish(AgentEvent.create("routine", str(index), (), {}))

    assert len(bus.recent(100)) == 30


def test_audit_events_are_retained_without_routine_expiry() -> None:
    bus = EventBus(max_events=2, routine_ttl=timedelta(seconds=1))
    event = AgentEvent.create("audit", "important", (), {}, audit_worthy=True)
    object.__setattr__(event, "occurred_at", datetime.now(UTC) - timedelta(days=1))
    bus.publish(event)
    assert bus.recent() == (event,)


def test_repository_persists_only_audit_events_and_is_immutable(tmp_path) -> None:
    database = Database(tmp_path / "events.db")
    database.migrate()
    repository = AgentEventRepository(database)
    routine = AgentEvent.create("routine", "no", (), {})
    audit = AgentEvent.create("audit", "yes", ("CODE",), {"n": 1}, audit_worthy=True)

    repository.save(routine)
    repository.save(audit)
    assert repository.list_events() == (audit,)

    with (
        pytest.raises(sqlite3.IntegrityError, match="agent events are immutable"),
        database.transaction() as connection,
    ):
        connection.execute("DELETE FROM agent_events")
