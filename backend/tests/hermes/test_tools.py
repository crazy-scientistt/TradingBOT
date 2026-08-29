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


@pytest.mark.asyncio
async def test_run_backtest_does_not_fabricate_performance() -> None:
    registry = HermesToolRegistry()
    result = await registry.call("run_backtest", {"genome_id": "g-1"})
    assert result["available"] is False
    assert "sharpe" not in result
    assert result.get("win_rate") is None
    assert result["trades"] == []


@pytest.mark.asyncio
async def test_get_evaluation_does_not_auto_pass() -> None:
    registry = HermesToolRegistry()
    result = await registry.call("get_evaluation", {"partition": "development"})
    assert result["available"] is False
    assert result["passed"] is False


@pytest.mark.asyncio
async def test_submit_genome_unbound_is_rejected() -> None:
    registry = HermesToolRegistry()
    result = await registry.call("submit_genome", {"genome": {"genome_id": "g-1"}})
    assert result["available"] is False
    assert result["status"] == "rejected"
    assert result["reason"] == "GENOME_SERVICE_NOT_BOUND"
