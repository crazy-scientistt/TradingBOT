from __future__ import annotations

from datetime import timedelta
from typing import Annotated

from fastapi import Cookie, Depends, Header, HTTPException, Request, Response

from goldguard.security.models import (
    AuthenticationThrottled,
    AuthPrincipal,
    AuthSession,
    CsrfValidationError,
    RecentTotpRequired,
    SessionExpired,
    SessionTokens,
    TotpRequired,
)
from goldguard.security.service import AuthService

COOKIE_NAME = "gg_session"
CSRF_HEADER_NAME = "X-CSRF-Token"

_auth_service: AuthService | None = None


def configure_auth_service(service: AuthService) -> None:
    """Install the process-local service used by FastAPI dependencies."""

    global _auth_service
    _auth_service = service


def get_auth_service() -> AuthService:
    if _auth_service is None:
        raise RuntimeError("authentication service is not configured")
    return _auth_service


def require_mutation_auth(
    request: Request,
    session_cookie: Annotated[str | None, Cookie(alias=COOKIE_NAME)] = None,
    csrf_header: Annotated[str | None, Header(alias=CSRF_HEADER_NAME)] = None,
) -> AuthPrincipal:
    try:
        return get_auth_service().authenticate_mutation(session_cookie, csrf_header, request)
    except SessionExpired as exc:
        raise HTTPException(status_code=401, detail="authentication required") from exc
    except AuthenticationThrottled as exc:
        raise HTTPException(status_code=401, detail="authentication required") from exc
    except (CsrfValidationError, RecentTotpRequired, TotpRequired) as exc:
        raise HTTPException(status_code=403, detail="forbidden") from exc


def require_sensitive_mutation_auth(
    principal: Annotated[AuthPrincipal, Depends(require_mutation_auth)],
) -> AuthPrincipal:
    try:
        get_auth_service().require_recent_totp(
            principal.session_id,
            max_age=timedelta(minutes=5),
            correlation_id=principal.correlation_id,
        )
    except RecentTotpRequired as exc:
        raise HTTPException(status_code=403, detail="recent 2FA verification required") from exc
    except (SessionExpired, AuthenticationThrottled) as exc:
        raise HTTPException(status_code=401, detail="authentication required") from exc
    return principal


def set_session_cookie(
    response: Response,
    tokens: SessionTokens | AuthSession,
    *,
    production: bool | None = None,
) -> None:
    """Set the opaque session cookie with strict browser security metadata."""

    secure = get_auth_service().production if production is None else production
    now = get_auth_service().current_time()
    absolute = tokens.absolute_expires_at or tokens.expires_at
    max_age = max(0, int((absolute - now).total_seconds()))
    response.set_cookie(
        key=COOKIE_NAME,
        value=tokens.cookie_token,
        max_age=max_age,
        httponly=True,
        secure=secure,
        samesite="strict",
        path="/",
    )


def clear_session_cookie(response: Response) -> None:
    response.delete_cookie(
        key=COOKIE_NAME,
        httponly=True,
        secure=get_auth_service().production,
        samesite="strict",
        path="/",
    )
