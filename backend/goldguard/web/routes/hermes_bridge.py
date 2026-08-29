from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Header, HTTPException, Request

from goldguard.hermes.tools import (
    ForbiddenHermesToolError,
    HermesToolRegistry,
    SealedHoldoutAccessError,
)

router = APIRouter(prefix="/internal/hermes/tools", tags=["hermes_bridge"])

_tool_registry = HermesToolRegistry()


@router.post("/{tool_name}")
async def execute_hermes_tool(
    tool_name: str,
    payload: dict[str, Any],
    request: Request,
    authorization: str | None = Header(default=None),
) -> dict[str, Any]:
    try:
        res = await _tool_registry.call(tool_name, payload)
        return res
    except SealedHoldoutAccessError as exc:
        raise HTTPException(
            status_code=403,
            detail={"code": "SEALED_HOLDOUT", "message": str(exc)},
        ) from exc
    except ForbiddenHermesToolError as exc:
        raise HTTPException(
            status_code=403,
            detail={"code": "FORBIDDEN_TOOL", "message": str(exc)},
        ) from exc
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

