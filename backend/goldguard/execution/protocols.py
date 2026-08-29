from __future__ import annotations

from typing import Protocol

from goldguard.domain.enums import ExitReason
from goldguard.execution.models import (
    AccountSnapshot,
    ExecutionResult,
    OrderIntent,
    OrderRecord,
)


class ExecutionBroker(Protocol):
    async def submit(self, intent: OrderIntent) -> ExecutionResult: ...
    async def cancel(self, client_order_id: str) -> OrderRecord: ...
    async def close(self, position_id: str, reason: ExitReason) -> ExecutionResult: ...
    async def snapshot(self) -> AccountSnapshot: ...

