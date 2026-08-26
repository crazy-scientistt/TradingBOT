from datetime import UTC, datetime, timedelta

from goldguard.observability.events import AgentEvent, EventBus


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


def test_audit_events_are_retained_without_routine_expiry() -> None:
    bus = EventBus(max_events=2, routine_ttl=timedelta(seconds=1))
    event = AgentEvent.create("audit", "important", (), {}, audit_worthy=True)
    object.__setattr__(event, "occurred_at", datetime.now(UTC) - timedelta(days=1))
    bus.publish(event)
    assert bus.recent() == (event,)
