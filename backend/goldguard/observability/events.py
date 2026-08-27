"""Typed, bounded agent event stream with optional durable audit storage."""

from __future__ import annotations

import asyncio
from collections import deque
from collections.abc import AsyncGenerator, Mapping
from contextlib import suppress
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from types import MappingProxyType
from typing import Any, Protocol
from uuid import uuid4


class EventSink(Protocol):
    def save(self, event: AgentEvent) -> None: ...


@dataclass(frozen=True, slots=True)
class AgentEvent:
    event_id: str
    action: str
    reason: str
    reason_codes: tuple[str, ...]
    payload: Mapping[str, Any]
    occurred_at: datetime
    audit_worthy: bool = False

    def __post_init__(self) -> None:
        when = self.occurred_at
        if when.tzinfo is None:
            object.__setattr__(self, "occurred_at", when.replace(tzinfo=UTC))
        if not isinstance(self.reason_codes, tuple):
            object.__setattr__(self, "reason_codes", tuple(self.reason_codes))
        if not isinstance(self.payload, MappingProxyType):
            object.__setattr__(self, "payload", MappingProxyType(dict(self.payload)))

    @classmethod
    def create(
        cls,
        action: str,
        reason: str,
        reason_codes: tuple[str, ...] | list[str],
        payload: Mapping[str, Any],
        *,
        audit_worthy: bool = False,
        occurred_at: datetime | None = None,
    ) -> AgentEvent:
        when = occurred_at or datetime.now(UTC)
        if when.tzinfo is None:
            when = when.replace(tzinfo=UTC)
        return cls(
            event_id=str(uuid4()),
            action=action,
            reason=reason,
            reason_codes=tuple(reason_codes),
            payload=MappingProxyType(dict(payload)),
            occurred_at=when,
            audit_worthy=audit_worthy,
        )


class EventBus:
    def __init__(
        self,
        *,
        max_events: int = 1000,
        routine_ttl: timedelta = timedelta(hours=1),
        subscriber_queue_size: int = 100,
        sink: EventSink | None = None,
    ) -> None:
        if max_events < 1 or subscriber_queue_size < 1:
            raise ValueError("event capacities must be positive")
        self._events: deque[AgentEvent] = deque(maxlen=max_events)
        self._routine_ttl = routine_ttl
        self._subscriber_queue_size = subscriber_queue_size
        self._subscribers: set[asyncio.Queue[AgentEvent | None]] = set()
        self._sink = sink

    def publish(self, event: AgentEvent) -> None:
        self._events.append(event)
        if event.audit_worthy and self._sink is not None:
            self._sink.save(event)
        for queue in tuple(self._subscribers):
            if queue.full():
                with suppress(asyncio.QueueEmpty):
                    queue.get_nowait()
            with suppress(asyncio.QueueFull):
                queue.put_nowait(event)

    def recent(self, limit: int = 30) -> tuple[AgentEvent, ...]:
        if limit <= 0:
            return ()
        limit = min(limit, 30)
        cutoff = datetime.now(UTC) - self._routine_ttl
        events = [
            event for event in self._events if event.audit_worthy or event.occurred_at >= cutoff
        ]
        self._events.clear()
        self._events.extend(events)
        return tuple(events[-limit:])

    async def subscribe(self) -> AsyncGenerator[AgentEvent, None]:
        queue: asyncio.Queue[AgentEvent | None] = asyncio.Queue(maxsize=self._subscriber_queue_size)
        self._subscribers.add(queue)
        try:
            while True:
                event = await queue.get()
                if event is None:
                    return
                yield event
        finally:
            self._subscribers.discard(queue)
