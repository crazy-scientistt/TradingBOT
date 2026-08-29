from __future__ import annotations

import json
from typing import Any

MAX_PAYLOAD_BYTES = 16_384


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

    def __init__(self, bindings: dict[str, Any] | None = None) -> None:
        self._bindings = bindings or {}

    def names(self) -> frozenset[str]:
        return self.ALLOWED_TOOLS

    async def call(
        self, tool_name: str, payload: dict[str, Any], principal: Any = None
    ) -> dict[str, Any]:
        if tool_name not in self.ALLOWED_TOOLS:
            raise ForbiddenHermesToolError(f"tool {tool_name} is forbidden or does not exist")

        encoded = json.dumps(payload, default=str).encode("utf-8")
        if len(encoded) > MAX_PAYLOAD_BYTES:
            return {"available": False, "reason": "PAYLOAD_TOO_LARGE"}

        if tool_name == "get_evaluation" and payload.get("partition") == "holdout":
            raise SealedHoldoutAccessError("sealed holdout partition access is strictly forbidden")

        bound = self._bindings.get(tool_name)
        if bound is not None:
            return await bound(payload, principal)

        if tool_name == "get_candles":
            return {
                "available": False,
                "reason": "MARKET_STORE_NOT_BOUND",
                "candles": [],
                "symbol": payload.get("symbol", "PAXGUSDT"),
            }
        if tool_name == "get_features":
            return {"available": False, "reason": "FEATURE_STORE_NOT_BOUND", "features": {}}
        if tool_name == "get_evidence":
            return {"available": False, "reason": "EVIDENCE_STORE_NOT_BOUND", "evidence": []}
        if tool_name == "get_trade_outcomes":
            return {"available": False, "reason": "OUTCOME_STORE_NOT_BOUND", "trades": []}
        if tool_name == "get_lessons":
            return {"available": False, "reason": "LESSON_STORE_NOT_BOUND", "lessons": []}
        if tool_name == "run_backtest":
            return {
                "available": False,
                "reason": "BACKTEST_RUNNER_NOT_BOUND",
                "trades": [],
            }
        if tool_name == "get_evaluation":
            return {
                "available": False,
                "reason": "EVALUATION_NOT_BOUND",
                "partition": payload.get("partition", "development"),
                "passed": False,
            }
        if tool_name == "submit_genome":
            return {
                "available": False,
                "reason": "GENOME_SERVICE_NOT_BOUND",
                "status": "rejected",
            }
        return {"available": False, "reason": "UNKNOWN_TOOL"}
