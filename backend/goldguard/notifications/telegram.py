from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

import httpx
from pydantic import SecretStr

CATEGORIES = (
    "emergency",
    "breaker",
    "protection",
    "live_arm",
    "fill",
    "daily_summary",
    "research",
)

CRITICAL_CATEGORIES = frozenset({"emergency", "breaker", "protection", "live_arm"})

TelegramTransport = Callable[[str], Awaitable[bool]]


class CriticalCategoryMuteError(ValueError):
    """Raised when a caller tries to mute a critical alert category."""


class TelegramNotificationService:
    def __init__(
        self,
        bot_token: SecretStr | None = None,
        chat_id: str | None = None,
        enabled: bool = True,
        transport: TelegramTransport | None = None,
    ) -> None:
        self._bot_token = bot_token
        self.chat_id = chat_id
        self.enabled = enabled
        self._transport = transport
        self._preferences: dict[str, bool] = {category: True for category in CATEGORIES}

    @property
    def bot_token(self) -> SecretStr | None:
        return self._bot_token

    def __repr__(self) -> str:
        return (
            "TelegramNotificationService("
            f"chat_id={self.chat_id!r}, enabled={self.enabled}, token=redacted)"
        )

    def __str__(self) -> str:
        return self.__repr__()

    def is_critical(self, category: str) -> bool:
        return category in CRITICAL_CATEGORIES

    def is_allowed(self, category: str) -> bool:
        if category not in CATEGORIES:
            return False
        if not self.enabled:
            return False
        if category in CRITICAL_CATEGORIES:
            return True
        return self._preferences.get(category, False)

    def set_preference(self, category: str, enabled: bool) -> None:
        if category not in CATEGORIES:
            raise ValueError(f"unknown telegram category: {category}")
        if self.enabled and category in CRITICAL_CATEGORIES and enabled is False:
            raise CriticalCategoryMuteError(
                f"cannot mute critical category {category} while telegram is enabled"
            )
        self._preferences[category] = enabled

    async def notify(self, category: str, text: str) -> bool:
        if not self.is_allowed(category):
            return False
        return await self.send_message(text)

    async def send_message(self, text: str) -> bool:
        if self._transport is not None:
            return await self._transport(text)
        if not self._bot_token or not self.chat_id:
            return False
        token = self._bot_token.get_secret_value()
        url = f"https://api.telegram.org/bot{token}/sendMessage"
        payload: dict[str, Any] = {
            "chat_id": self.chat_id,
            "text": text,
            "parse_mode": "HTML",
        }
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                res = await client.post(url, json=payload)
                return res.status_code == 200
        except Exception:
            # Swallow delivery errors without chaining; token is never re-raised.
            return False
