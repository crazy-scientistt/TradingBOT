from __future__ import annotations

import pytest
from goldguard.notifications.telegram import (
    CRITICAL_CATEGORIES,
    CriticalCategoryMuteError,
    TelegramNotificationService,
)
from pydantic import SecretStr

SECRET = "super-secret-bot-token-do-not-leak"


def test_cannot_mute_critical_when_telegram_enabled() -> None:
    service = TelegramNotificationService(
        bot_token=SecretStr(SECRET),
        chat_id="123",
        enabled=True,
    )
    for category in CRITICAL_CATEGORIES:
        with pytest.raises(CriticalCategoryMuteError):
            service.set_preference(category, False)
        assert service.is_allowed(category) is True


def test_non_critical_category_can_be_muted() -> None:
    service = TelegramNotificationService(enabled=True)
    service.set_preference("research", False)
    assert service.is_allowed("research") is False
    assert service.is_allowed("fill") is True
    assert service.is_allowed("emergency") is True


@pytest.mark.asyncio
async def test_notify_respects_preferences_without_network() -> None:
    sent: list[str] = []

    async def transport(text: str) -> bool:
        sent.append(text)
        return True

    service = TelegramNotificationService(enabled=True, transport=transport)
    service.set_preference("daily_summary", False)

    assert await service.notify("daily_summary", "quiet") is False
    assert await service.notify("breaker", "tripped") is True
    assert sent == ["tripped"]


def test_token_never_appears_in_repr() -> None:
    service = TelegramNotificationService(
        bot_token=SecretStr(SECRET),
        chat_id="42",
        enabled=True,
    )
    rendered = repr(service) + str(service)
    assert SECRET not in rendered
    assert "redacted" in repr(service)


@pytest.mark.asyncio
async def test_notification_never_contains_secret() -> None:
    sent: list[str] = []

    async def transport(text: str) -> bool:
        sent.append(text)
        return True

    service = TelegramNotificationService(enabled=True, transport=transport)
    leaked = f"token={SECRET} bearer abcdefghijklmnop"
    await service.notify("fill", leaked)
    assert sent
    assert SECRET not in sent[0]
