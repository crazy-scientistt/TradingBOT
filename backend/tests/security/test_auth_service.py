from datetime import UTC, datetime, timedelta
from pathlib import Path

import pyotp
import pytest
from goldguard.security.models import (
    AuthenticationThrottled,
    CsrfValidationError,
    InvalidCredentials,
    RecentTotpRequired,
    SessionExpired,
)
from goldguard.security.service import AuthService
from goldguard.storage.database import Database
from pydantic import SecretStr


@pytest.fixture
def auth_service(tmp_path: Path) -> AuthService:
    database = Database(tmp_path / "auth.db")
    database.migrate()
    service = AuthService(database, now=lambda: datetime.now(UTC))
    service.bootstrap_admin(
        SecretStr("correct horse battery staple"),
        SecretStr(pyotp.random_base32()),
    )
    return service


def test_login_cookie_and_csrf_are_distinct(auth_service: AuthService) -> None:
    tokens = auth_service.login(SecretStr("correct horse battery staple"), "127.0.0.1", "test")

    assert tokens.cookie_token != tokens.csrf_token
    assert tokens.session_id == tokens.cookie_token
    assert tokens.cookie_token not in repr(tokens)
    assert tokens.csrf_token not in repr(tokens)


def test_password_is_argon2_hashed_and_raw_session_values_are_not_stored(
    auth_service: AuthService,
) -> None:
    tokens = auth_service.login(SecretStr("correct horse battery staple"), "127.0.0.1", "test")

    with auth_service.database.connect() as connection:
        admin = connection.execute("SELECT password_hash FROM admin_users").fetchone()
        session = connection.execute(
            "SELECT session_hash, csrf_hash FROM admin_sessions"
        ).fetchone()

    assert admin is not None and str(admin["password_hash"]).startswith("$argon2")
    assert session is not None
    assert tokens.cookie_token not in str(session["session_hash"])
    assert tokens.csrf_token not in str(session["csrf_hash"])


def test_sensitive_action_requires_recent_totp(auth_service: AuthService) -> None:
    tokens = auth_service.login(SecretStr("correct horse battery staple"), "127.0.0.1", "test")

    with pytest.raises(RecentTotpRequired):
        auth_service.require_recent_totp(tokens.session_id, timedelta(minutes=5))


def test_successful_totp_rotates_session_and_marks_recent_totp(auth_service: AuthService) -> None:
    tokens = auth_service.login(SecretStr("correct horse battery staple"), "127.0.0.1", "test")
    with auth_service.database.connect() as connection:
        secret = connection.execute("SELECT totp_secret FROM admin_users").fetchone()[0]

    authenticated = auth_service.verify_totp(tokens.session_id, pyotp.TOTP(secret).now())

    assert authenticated.session_id != tokens.session_id
    auth_service.require_recent_totp(authenticated.session_id, timedelta(minutes=5))
    with pytest.raises(SessionExpired):
        auth_service.authenticate(tokens.session_id)


def test_idle_and_absolute_expiry_are_enforced(tmp_path: Path) -> None:
    database = Database(tmp_path / "expiry.db")
    database.migrate()
    current = datetime(2026, 8, 29, tzinfo=UTC)
    service = AuthService(
        database,
        now=lambda: current,
        idle_timeout=timedelta(minutes=5),
        absolute_timeout=timedelta(minutes=10),
    )
    service.bootstrap_admin(
        SecretStr("correct horse battery staple"), SecretStr(pyotp.random_base32())
    )
    tokens = service.login(SecretStr("correct horse battery staple"), "127.0.0.1", "test")

    current += timedelta(minutes=4)
    service.authenticate(tokens.session_id)
    current += timedelta(minutes=5, seconds=1)
    with pytest.raises(SessionExpired):
        service.authenticate(tokens.session_id)


def test_failed_password_attempts_are_throttled(auth_service: AuthService) -> None:
    for _ in range(auth_service.password_failure_limit):
        with pytest.raises((AuthenticationThrottled, InvalidCredentials)):
            auth_service.login(SecretStr("wrong password"), "127.0.0.1", "test")

    with pytest.raises(AuthenticationThrottled):
        auth_service.login(SecretStr("correct horse battery staple"), "127.0.0.1", "test")


def test_csrf_is_hash_compared_and_distinct_from_cookie(auth_service: AuthService) -> None:
    tokens = auth_service.login(SecretStr("correct horse battery staple"), "127.0.0.1", "test")

    with pytest.raises(CsrfValidationError):
        auth_service.authenticate_mutation(tokens.cookie_token, "wrong", ip="127.0.0.1")

    principal = auth_service.authenticate_mutation(
        tokens.cookie_token,
        tokens.csrf_token,
        ip="127.0.0.1",
    )
    assert principal.username == "admin"
