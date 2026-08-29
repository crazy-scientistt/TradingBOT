from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Header, HTTPException, Request

from goldguard.config import Settings
from goldguard.hermes.tools import (
    ForbiddenHermesToolError,
    HermesToolRegistry,
    SealedHoldoutAccessError,
)

router = APIRouter(prefix="/internal/hermes/tools", tags=["hermes_bridge"])

_tool_registry = HermesToolRegistry()


def configure_tool_registry(registry: HermesToolRegistry) -> None:
    global _tool_registry
    _tool_registry = registry


def get_tool_registry() -> HermesToolRegistry:
    return _tool_registry


def _require_bridge_auth(authorization: str | None) -> None:
    settings = Settings()
    token = settings.hermes_bridge_token
    if token is None:
        raise HTTPException(
            status_code=503,
            detail={"code": "BRIDGE_TOKEN_UNCONFIGURED", "message": "hermes bridge token missing"},
        )
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(
            status_code=401,
            detail={"code": "BRIDGE_AUTH_REQUIRED", "message": "bearer token required"},
        )
    given = authorization.removeprefix("Bearer ").strip()
    if given != token.get_secret_value():
        raise HTTPException(
            status_code=403,
            detail={"code": "BRIDGE_AUTH_REJECTED", "message": "bearer token rejected"},
        )


@router.post("/{tool_name}")
async def execute_hermes_tool(
    tool_name: str,
    payload: dict[str, Any],
    request: Request,
    authorization: str | None = Header(default=None),
) -> dict[str, Any]:
    _ = request
    _require_bridge_auth(authorization)
    try:
        return await get_tool_registry().call(tool_name, payload)
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
