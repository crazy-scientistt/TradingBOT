from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

import pytest
from goldguard.execution.order_manager import ManagedStatus, OrderManager


@dataclass
class UpdateMock:
    client_order_id: str
    filled: Decimal


@pytest.mark.asyncio
async def test_each_partial_fill_is_protected_once() -> None:
    manager = OrderManager()
    upd1 = UpdateMock(client_order_id="gg-1", filled=Decimal("0.4"))
    res1 = await manager.on_update(upd1)
    assert res1.status == ManagedStatus.ACTIVE
    assert res1.protected_quantity == Decimal("0.4")

