from __future__ import annotations

import pytest
from goldguard.hermes.tools import (
    HermesToolRegistry,
    SealedHoldoutAccessError,
)


@pytest.mark.parametrize("forbidden", ["broker", "secret", "settings", "shell", "delete"])
def test_bridge_exposes_no_forbidden_tool(forbidden: str) -> None:
    tool_registry = HermesToolRegistry()
    assert all(forbidden not in name.lower() for name in tool_registry.names())


@pytest.mark.asyncio
async def test_holdout_query_is_always_rejected() -> None:
    tool_registry = HermesToolRegistry()
    with pytest.raises(SealedHoldoutAccessError):
        await tool_registry.call("get_evaluation", {"partition": "holdout"})

