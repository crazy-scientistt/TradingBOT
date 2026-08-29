from __future__ import annotations

from typing import Any


class HermesSupervisor:
    def __init__(self, loop_service: Any = None) -> None:
        self.loop_service = loop_service
        self._quota_exhausted = False

    def consume_all_daily_iterations(self) -> None:
        self._quota_exhausted = True

    async def tick(self) -> Any:
        if self._quota_exhausted:
            return type("Result", (), {"code": "QUOTA_EXHAUSTED"})()
        return type("Result", (), {"code": "SUCCESS"})()

