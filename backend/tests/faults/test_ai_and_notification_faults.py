from __future__ import annotations

import pytest
from goldguard.notifications.telegram import TelegramNotificationService


@pytest.mark.asyncio
async def test_telegram_outage_does_not_block_critical_preference() -> None:
    async def down(_text: str) -> bool:
        raise ConnectionError("telegram unreachable")

    service = TelegramNotificationService(enabled=True, transport=down)
    sent = await service.notify("emergency", "halt")
    assert sent is False
    assert service.is_allowed("emergency") is True


@pytest.mark.asyncio
async def test_provider_outage_tool_stays_unavailable() -> None:
    from goldguard.hermes.tools import HermesToolRegistry

    registry = HermesToolRegistry()
    result = await registry.call("get_features", {})
    assert result["available"] is False
    assert result["reason"] == "FEATURE_STORE_NOT_BOUND"
