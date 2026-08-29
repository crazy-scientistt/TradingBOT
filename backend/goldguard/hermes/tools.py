from __future__ import annotations

from typing import Any


class SealedHoldoutAccessError(PermissionError):
    pass


class ForbiddenHermesToolError(PermissionError):
    pass


class HermesToolRegistry:
    ALLOWED_TOOLS = frozenset(
        {
            "get_candles",
            "get_features",
            "get_evidence",
            "get_trade_outcomes",
            "get_lessons",
            "run_backtest",
            "get_evaluation",
            "submit_genome",
        }
    )

    def names(self) -> frozenset[str]:
        return self.ALLOWED_TOOLS

    async def call(
        self, tool_name: str, payload: dict[str, Any], principal: Any = None
    ) -> dict[str, Any]:
        if tool_name not in self.ALLOWED_TOOLS:
            raise ForbiddenHermesToolError(f"tool {tool_name} is forbidden or does not exist")

        if tool_name == "get_evaluation" and payload.get("partition") == "holdout":
            raise SealedHoldoutAccessError("sealed holdout partition access is strictly forbidden")

        if tool_name == "get_candles":
            return {"candles": [], "symbol": payload.get("symbol", "PAXGUSDT")}
        elif tool_name == "get_features":
            return {"features": {}, "regime": "trend"}
        elif tool_name == "get_evidence":
            return {"evidence": []}
        elif tool_name == "get_trade_outcomes":
            return {"trades": []}
        elif tool_name == "get_lessons":
            return {"lessons": []}
        elif tool_name == "run_backtest":
            return {"sharpe": 1.5, "win_rate": 0.60, "max_drawdown": 0.02}
        elif tool_name == "get_evaluation":
            return {"passed": True, "partition": payload.get("partition", "development")}
        elif tool_name == "submit_genome":
            genome_data = payload.get("genome", {})
            return {
                "genome_id": genome_data.get("genome_id", "gen-submitted"),
                "status": "candidate",
            }

        return {}

