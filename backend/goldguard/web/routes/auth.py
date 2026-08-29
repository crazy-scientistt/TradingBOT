from __future__ import annotations

import contextlib
import uuid
from typing import Annotated

from fastapi import APIRouter, Cookie, HTTPException, Request, Response
from pydantic import SecretStr

from goldguard.security.models import (
    AuthenticationError,
    AuthenticationThrottled,
    InvalidCredentials,
    SessionExpired,
    TotpRequired,
)
from goldguard.web.auth_dependencies import (
    COOKIE_NAME,
    clear_session_cookie,
    get_auth_service,
    set_session_cookie,
)
from goldguard.web.schemas.control import (
    AuthSessionResponse,
    LoginRequest,
    TotpVerifyRequest,
)

router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.post("/login", response_model=AuthSessionResponse)
def login(
    payload: LoginRequest,
    request: Request,
    response: Response,
) -> AuthSessionResponse:
    service = get_auth_service()
    client_ip = request.client.host if request.client else "127.0.0.1"
    user_agent = request.headers.get("user-agent", "unknown")
    correlation = str(uuid.uuid4())

    try:
        tokens = service.login(
            SecretStr(payload.password),
            ip=client_ip,
            user_agent=user_agent,
            correlation_id=correlation,
        )
    except AuthenticationThrottled as exc:
        raise HTTPException(status_code=429, detail="too many failed attempts") from exc
    except InvalidCredentials as exc:
        raise HTTPException(status_code=401, detail="invalid credentials") from exc
    except AuthenticationError as exc:
        raise HTTPException(status_code=401, detail="authentication failed") from exc

    set_session_cookie(response, tokens)

    return AuthSessionResponse(
        authenticated=True,
        username=service.username,
        totp_required=True,
        totp_verified=False,
        expires_at=tokens.expires_at.isoformat(),
        absolute_expires_at=(
            tokens.absolute_expires_at.isoformat()
            if tokens.absolute_expires_at
            else None
        ),
        csrf_token=tokens.csrf_token,
    )


@router.post("/totp", response_model=AuthSessionResponse)
def verify_totp(
    payload: TotpVerifyRequest,
    request: Request,
    response: Response,
    session_cookie: Annotated[str | None, Cookie(alias=COOKIE_NAME)] = None,
) -> AuthSessionResponse:
    if not session_cookie:
        raise HTTPException(status_code=401, detail="session is missing")

    service = get_auth_service()
    correlation = str(uuid.uuid4())

    try:
        session = service.verify_totp(
            session_cookie,
            code=payload.code,
            correlation_id=correlation,
        )
    except AuthenticationThrottled as exc:
        raise HTTPException(status_code=429, detail="too many failed attempts") from exc
    except (TotpRequired, InvalidCredentials, SessionExpired) as exc:
        raise HTTPException(status_code=401, detail="invalid or expired code") from exc
    except AuthenticationError as exc:
        raise HTTPException(status_code=401, detail="authentication failed") from exc

    set_session_cookie(response, session)
    response.headers["X-CSRF-Token"] = session.csrf_token

    return AuthSessionResponse(
        authenticated=True,
        username=session.username,
        totp_required=True,
        totp_verified=True,
        expires_at=session.expires_at.isoformat(),
        absolute_expires_at=session.absolute_expires_at.isoformat(),
        csrf_token=session.csrf_token,
    )


@router.post("/logout")
def logout(
    response: Response,
    session_cookie: Annotated[str | None, Cookie(alias=COOKIE_NAME)] = None,
) -> dict[str, str]:
    if session_cookie:
        with contextlib.suppress(Exception):
            get_auth_service().revoke(session_cookie)
    clear_session_cookie(response)
    return {"status": "logged_out"}


@router.get("/session", response_model=AuthSessionResponse)
def get_session(
    session_cookie: Annotated[str | None, Cookie(alias=COOKIE_NAME)] = None,
) -> AuthSessionResponse:
    if not session_cookie:
        return AuthSessionResponse(authenticated=False, totp_verified=False)

    try:
        service = get_auth_service()
        session = service.authenticate(session_cookie)
        return AuthSessionResponse(
            authenticated=True,
            username=session.username,
            totp_required=True,
            totp_verified=session.last_totp_at is not None,
            expires_at=session.expires_at.isoformat(),
            absolute_expires_at=session.absolute_expires_at.isoformat(),
            csrf_token=session.csrf_token,
        )
    except Exception:
        return AuthSessionResponse(authenticated=False, totp_verified=False)

