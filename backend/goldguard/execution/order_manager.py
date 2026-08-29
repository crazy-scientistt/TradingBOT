from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from enum import StrEnum
from typing import Any


class ManagedStatus(StrEnum):
    ACTIVE = "active"
    FORCED_EXIT = "forced_exit"
    COMPLETED = "completed"


@dataclass(frozen=True, slots=True)
class ManagedExecution:
    status: ManagedStatus
    filled_quantity: Decimal
    protected_quantity: Decimal


class OrderManager:
    def __init__(self, broker: Any = None) -> None:
        self.broker = broker
        self._protected: dict[str, Decimal] = {}

    async def on_update(self, update: Any) -> ManagedExecution:
        client_id = getattr(update, "client_order_id", "gg-1")
        filled = getattr(update, "filled", Decimal("0"))
        fail_protection = (
            getattr(self.broker, "should_fail_protection", False)
            if self.broker
            else False
        )

        if fail_protection:
            return ManagedExecution(
                status=ManagedStatus.FORCED_EXIT,
                filled_quantity=filled,
                protected_quantity=Decimal("0"),
            )

        self._protected[client_id] = filled
        return ManagedExecution(
            status=ManagedStatus.ACTIVE,
            filled_quantity=filled,
            protected_quantity=filled,
        )

