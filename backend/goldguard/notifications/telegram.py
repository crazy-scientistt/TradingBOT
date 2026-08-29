from __future__ import annotations

import httpx
from pydantic import SecretStr


class TelegramNotificationService:
    def __init__(
        self, bot_token: SecretStr | None = None, chat_id: str | None = None
    ) -> None:
        self.bot_token = bot_token
        self.chat_id = chat_id

    async def send_message(self, text: str) -> bool:
        if not self.bot_token or not self.chat_id:
            return False
        token = self.bot_token.get_secret_value()
        url = f"https://api.telegram.org/bot{token}/sendMessage"
        payload = {"chat_id": self.chat_id, "text": text, "parse_mode": "HTML"}
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                res = await client.post(url, json=payload)
                return res.status_code == 200
        except Exception:
            return False

