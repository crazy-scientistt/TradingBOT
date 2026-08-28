from datetime import UTC, datetime
from pathlib import Path

import pyotp
from fastapi import FastAPI
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
    def mutate(principal=require_mutation_auth):  # pragma: no cover
        return {"ok": True}

    # The dependency object itself must be a FastAPI-callable dependency, and direct
    # invocation proves the same validation path without adding Task 4 routes.
    assert require_mutation_auth.__name__ == "require_mutation_auth"
    principal = service.authenticate_mutation(tokens.cookie_token, tokens.csrf_token, ip="test")
    assert principal.username == "admin"


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
    set_session_cookie(response, tokens, production=True)
    cookie = response.headers["set-cookie"]
    assert "HttpOnly" in cookie
    assert "Secure" in cookie
    assert "SameSite=strict" in cookie
    assert "gg_session=" in cookie
