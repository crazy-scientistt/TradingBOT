from __future__ import annotations

from typing import Any


class PromotionSupervisor:
    def __init__(self, system: Any = None) -> None:
        self.system = system

    async def tick(self) -> None:
        if self.system is not None:
            await self.system.on_supervisor_tick()

