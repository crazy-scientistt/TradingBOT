from __future__ import annotations

from decimal import Decimal
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException

from goldguard.domain.profile import default_autonomous_profile
from goldguard.security.models import AuthPrincipal
from goldguard.services.settings_service import (
    ProfileChangeBlocked,
    RuntimeSafetySnapshot,
    get_settings_service,
)
from goldguard.web.auth_dependencies import (
    require_mutation_auth,
    require_sensitive_mutation_auth,
)
from goldguard.web.schemas.control import (
    ProfilePreviewResponse,
    ProfileResponse,
    ProfileUpdate,
)

router = APIRouter(prefix="/api/settings", tags=["settings"])


def _risk_ceiling_increased(current: object, candidate: object) -> bool:
    from goldguard.domain.profile import AutonomousProfile

    if not isinstance(current, AutonomousProfile) or not isinstance(candidate, AutonomousProfile):
        return True
    return any(
        (
            candidate.risk.max_capital_per_trade_rate
            > current.risk.max_capital_per_trade_rate,
            candidate.risk.max_futures_leverage > current.risk.max_futures_leverage,
            candidate.risk.max_total_exposure_rate > current.risk.max_total_exposure_rate,
            candidate.risk.rolling_24h_loss_limit_rate
            > current.risk.rolling_24h_loss_limit_rate,
        )
    )


def _get_runtime_snapshot() -> RuntimeSafetySnapshot:
    from goldguard.web import app as app_module

    equity = Decimal("10000.00")
    if app_module._settings is not None:
        equity = app_module._settings.paper_starting_balance

    has_open_positions = False
    has_open_entry_orders = False
    live_armed = False

    if app_module._trading_runtime is not None:
        status = app_module._trading_runtime.status()
        has_open_positions = status.has_position
    elif app_module._broker is not None:
        has_open_positions = app_module._broker.position is not None

    if app_module._broker is not None:
        quote = app_module._market().latest_quote
        equity = (
            app_module._broker.equity(quote)
            if quote is not None
            else app_module._broker.cash
        )

    return RuntimeSafetySnapshot(
        has_open_positions=has_open_positions,
        has_open_entry_orders=has_open_entry_orders,
        live_armed=live_armed,
        account_equity_usdt=equity,
    )


@router.get("/profile", response_model=ProfileResponse)
def get_profile() -> ProfileResponse:
    service = get_settings_service()
    runtime = _get_runtime_snapshot()
    active = service._repository.active()
    if active is None:
        default_profile = default_autonomous_profile()
        active = service._repository.activate(
            default_profile, actor="system", correlation_id="init-profile"
        )

    preview = service.preview(active.profile, runtime)
    return ProfileResponse.from_active(
        active, equity=runtime.account_equity_usdt, blockers=preview.blockers
    )


@router.post("/profile/preview", response_model=ProfilePreviewResponse)
def preview_profile(payload: ProfileUpdate) -> ProfilePreviewResponse:
    service = get_settings_service()
    runtime = _get_runtime_snapshot()
    candidate = payload.to_domain()
    preview = service.preview(candidate, runtime)
    return ProfilePreviewResponse.from_preview(
        preview, equity=runtime.account_equity_usdt
    )


@router.post("/profile", response_model=ProfileResponse)
def activate_profile(
    payload: ProfileUpdate,
    principal: Annotated[AuthPrincipal, Depends(require_mutation_auth)],
) -> ProfileResponse:
    service = get_settings_service()
    runtime = _get_runtime_snapshot()
    candidate = payload.to_domain()
    current = service._repository.active()
    if current is None or _risk_ceiling_increased(current.profile, candidate):
        require_sensitive_mutation_auth(principal)
    try:
        active = service.activate(
            candidate,
            actor=principal.actor,
            correlation_id=principal.correlation_id,
            runtime=runtime,
        )
    except ProfileChangeBlocked as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc

    return ProfileResponse.from_active(active, equity=runtime.account_equity_usdt)

