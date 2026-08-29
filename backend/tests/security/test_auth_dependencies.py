from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Annotated

import pyotp
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient
from goldguard.security.models import AuthPrincipal
from goldguard.security.service import AuthService
from goldguard.storage.database import Database
from goldguard.web.auth_dependencies import (
    configure_auth_service,
    require_mutation_auth,
    set_session_cookie,
)
from pydantic import SecretStr


def test_mutation_dependency_requires_cookie_and_csrf(tmp_path: Path) -> None:
    database = Database(tmp_path / "deps.db")
    database.migrate()
    service = AuthService(database, now=lambda: datetime.now(UTC))
    service.bootstrap_admin(
        SecretStr("correct horse battery staple"), SecretStr(pyotp.random_base32())
    )
    configure_auth_service(service)
    tokens = service.login(SecretStr("correct horse battery staple"), "test", "ua")

    app = FastAPI()

    @app.post("/mutate")
    def mutate(
        principal: Annotated[AuthPrincipal, Depends(require_mutation_auth)],
    ):
        return {"ok": True}

    client = TestClient(app)
    assert client.post("/mutate").status_code == 401
    client.cookies.set("gg_session", tokens.cookie_token)
    client.headers.update({"X-CSRF-Token": "wrong"})
    assert client.post(
        "/mutate",
    ).status_code == 403
    client.headers.update({"X-CSRF-Token": tokens.csrf_token})
    valid = client.post(
        "/mutate",
    )
    assert valid.status_code == 200
    assert valid.json() == {"ok": True}


def test_session_cookie_metadata_changes_for_production(tmp_path: Path) -> None:
    database = Database(tmp_path / "cookie.db")
    database.migrate()
    service = AuthService(database, now=lambda: datetime.now(UTC))
    service.bootstrap_admin(
        SecretStr("correct horse battery staple"), SecretStr(pyotp.random_base32())
    )
    tokens = service.login(SecretStr("correct horse battery staple"), "test", "ua")

    from fastapi import Response

    response = Response()
    configure_auth_service(service)
    set_session_cookie(response, tokens, production=True)
    cookie = response.headers["set-cookie"]
    assert "HttpOnly" in cookie
    assert "Secure" in cookie
    assert "SameSite=strict" in cookie


def test_cookie_max_age_uses_absolute_expiry_and_injected_clock(tmp_path: Path) -> None:
    database = Database(tmp_path / "cookie-clock.db")
    database.migrate()
    current = datetime(2026, 8, 29, tzinfo=UTC)
    service = AuthService(
        database,
        now=lambda: current,
        idle_timeout=timedelta(minutes=5),
        absolute_timeout=timedelta(minutes=30),
    )
    service.bootstrap_admin(
        SecretStr("correct horse battery staple"), SecretStr(pyotp.random_base32())
    )
    tokens = service.login(SecretStr("correct horse battery staple"), "test", "ua")

    from fastapi import Response

    response = Response()
    configure_auth_service(service)
    set_session_cookie(response, tokens, production=False)
    cookie = response.headers["set-cookie"]
    assert "Max-Age=1800" in cookie
    assert "gg_session=" in cookie

    with database.connect() as connection:
        secret = connection.execute("SELECT totp_secret FROM admin_users").fetchone()[0]
    rotated = service.verify_totp(
        tokens.session_id,
        pyotp.TOTP(secret).at(int(current.timestamp())),
    )
    rotated_response = Response()
    set_session_cookie(rotated_response, rotated, production=False)
    assert "Max-Age=1800" in rotated_response.headers["set-cookie"]
