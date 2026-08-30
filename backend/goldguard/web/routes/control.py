from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException

from goldguard.domain.profile import default_autonomous_profile
from goldguard.live.arming import get_arming_service
from goldguard.live.models import ArmRequest, LiveArmingRejected
from goldguard.security.models import AuthPrincipal
from goldguard.services.preflight import PreflightService
from goldguard.services.settings_service import get_settings_service
from goldguard.web.auth_dependencies import (
    require_mutation_auth,
    require_sensitive_mutation_auth,
)

router = APIRouter(tags=["control"])

_preflight_service: PreflightService | None = None


def get_preflight_service() -> PreflightService:
    global _preflight_service
    if _preflight_service is None:
        _preflight_service = PreflightService()
    return _preflight_service


@router.post("/api/live/arm")
def arm_live(
    payload: ArmRequest,
    principal: Annotated[AuthPrincipal, Depends(require_mutation_auth)],
) -> dict[str, Any]:
    arming_service = get_arming_service()
    settings_service = get_settings_service()
    from goldguard.web import app as app_module

    settings = app_module._settings
    if settings is None or not settings.live_capability_enabled or settings.mode != "live":
        raise HTTPException(
            status_code=409,
            detail="live capability is disabled; paper remains the only execution mode",
        )
    active = settings_service._repository.active()
    profile = active.profile if active is not None else default_autonomous_profile()
    report = get_preflight_service().evaluate(profile)

    try:
        state = arming_service.arm(payload, principal, report)
    except LiveArmingRejected as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc

    return {
        "status": state.status.value,
        "profile_hash": state.profile_hash,
        "expected_equity_usdt": (
            str(state.expected_equity_usdt)
            if state.expected_equity_usdt is not None
            else None
        ),
        "armed_at": state.armed_at,
        "armed_by": state.armed_by,
        "new_entries_allowed": state.new_entries_allowed,
    }


@router.post("/api/live/disarm")
def disarm_live(
    principal: Annotated[AuthPrincipal, Depends(require_mutation_auth)],
) -> dict[str, Any]:
    arming_service = get_arming_service()
    state = arming_service.disarm(principal, reason="manual_disarm")
    return {
        "status": state.status.value,
        "profile_hash": None,
        "expected_equity_usdt": None,
        "armed_at": None,
        "armed_by": None,
        "new_entries_allowed": False,
    }


@router.post("/api/control/pause")
def control_pause(
    principal: Annotated[AuthPrincipal, Depends(require_mutation_auth)],
) -> dict[str, str]:
    from goldguard.web import app as app_module

    runtime = app_module._runtime_facade or app_module._trading_runtime
    if runtime is not None:
        runtime.pause()
    return {"status": "paused"}


@router.post("/api/control/cancel-all")
def control_cancel_all(
    principal: Annotated[AuthPrincipal, Depends(require_sensitive_mutation_auth)],
) -> dict[str, Any]:
    return {"status": "cancelled", "orders_cancelled": 0}


@router.post("/api/control/close-all")
def control_close_all(
    principal: Annotated[AuthPrincipal, Depends(require_sensitive_mutation_auth)],
) -> dict[str, Any]:
    from goldguard.web import app as app_module

    runtime = app_module._runtime_facade or app_module._trading_runtime
    count = 0
    if runtime is not None:
        before = runtime.status().has_position
        runtime.stop()
        count = 1 if before else 0
    return {"status": "positions_closed", "positions_closed_count": count}
