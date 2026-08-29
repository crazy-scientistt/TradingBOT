from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel, Field

from goldguard.notifications.telegram import (
    CATEGORIES,
    CRITICAL_CATEGORIES,
    TelegramNotificationService,
)

router = APIRouter(prefix="/api/telegram", tags=["telegram"])


class TelegramTestRequest(BaseModel):
    category: str = Field(default="daily_summary")
    text: str = Field(default="GoldGuard telegram test")


def _service() -> TelegramNotificationService:
    from goldguard.web import app as app_module

    settings = app_module._settings
    token = getattr(settings, "telegram_bot_token", None) if settings is not None else None
    chat_id = getattr(settings, "telegram_chat_id", None) if settings is not None else None
    return TelegramNotificationService(bot_token=token, chat_id=chat_id, enabled=True)


@router.get("/preferences")
def telegram_preferences() -> dict[str, Any]:
    service = _service()
    configured = bool(service.bot_token and service.chat_id)
    return {
        "availability": "available" if configured else "unavailable",
        "source": "telegram_service",
        "observed_at": datetime.now(UTC).isoformat(),
        "stale": False,
        "detail": None if configured else "bot token and chat id are operator-owned",
        "data": {
            "categories": list(CATEGORIES),
            "critical": sorted(CRITICAL_CATEGORIES),
            "enabled": service.enabled,
            "chat_configured": bool(service.chat_id),
            "token_configured": service.bot_token is not None,
        },
    }

@router.post("/test")
async def telegram_test(body: TelegramTestRequest) -> dict[str, Any]:
    service = _service()
    sent = await service.notify(body.category, body.text)
    return {
        "sent": sent,
        "category": body.category,
        "reason": None if sent else "TELEGRAM_NOT_CONFIGURED_OR_MUTED",
    }
