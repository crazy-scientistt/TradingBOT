import json
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pyotp
import pytest
from goldguard.security.models import (
    AdminAlreadyBootstrapped,
    AuthenticationThrottled,
    CsrfValidationError,
    InvalidCredentials,
    RecentTotpRequired,
    SessionExpired,
    TotpReplayRejected,
    TotpRequired,
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


def test_absolute_expiry_wins_over_repeated_idle_refresh(tmp_path: Path) -> None:
    database = Database(tmp_path / "absolute.db")
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
    current += timedelta(minutes=4)
    service.authenticate(tokens.session_id)
    current += timedelta(minutes=2, seconds=1)
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


def test_totp_replay_is_rejected_even_after_session_rotation(auth_service: AuthService) -> None:
    tokens = auth_service.login(SecretStr("correct horse battery staple"), "127.0.0.1", "test")
    with auth_service.database.connect() as connection:
        secret = connection.execute("SELECT totp_secret FROM admin_users").fetchone()[0]
    code = pyotp.TOTP(secret).now()

    rotated = auth_service.verify_totp(tokens.session_id, code)

    with pytest.raises(TotpReplayRejected):
        auth_service.verify_totp(rotated.session_id, code)


def test_totp_throttle_survives_a_fresh_password_session(auth_service: AuthService) -> None:
    tokens = auth_service.login(SecretStr("correct horse battery staple"), "127.0.0.1", "test")
    for _ in range(auth_service.totp_failure_limit):
        with pytest.raises(TotpRequired):
            auth_service.verify_totp(tokens.session_id, "000000")
    fresh = auth_service.login(SecretStr("correct horse battery staple"), "127.0.0.2", "test")

    with pytest.raises(AuthenticationThrottled):
        auth_service.verify_totp(fresh.session_id, "000000")


def test_security_events_are_redacted_and_cover_auth_lifecycle(auth_service: AuthService) -> None:
    password = "correct horse battery staple"
    tokens = auth_service.login(SecretStr(password), "127.0.0.1", "test")
    with auth_service.database.connect() as connection:
        totp_secret = str(connection.execute("SELECT totp_secret FROM admin_users").fetchone()[0])
    with pytest.raises(InvalidCredentials):
        auth_service.login(SecretStr("wrong password"), "127.0.0.1", "test")
    auth_service.authenticate_mutation(tokens.cookie_token, tokens.csrf_token, ip="127.0.0.1")
    auth_service.revoke(tokens.session_id)

    with auth_service.database.connect() as connection:
        rows = connection.execute(
            "SELECT event_type, actor, ip_address, user_agent, correlation_id, metadata "
            "FROM security_events ORDER BY id"
        ).fetchall()
    event_types = {str(row["event_type"]) for row in rows}
    assert {
        "admin_bootstrapped",
        "login_succeeded",
        "login_failed",
        "mutation_authenticated",
        "session_revoked",
    }.issubset(event_types)
    serialized = json.dumps([dict(row) for row in rows], sort_keys=True)
    assert password not in serialized
    assert tokens.cookie_token not in serialized
    assert tokens.csrf_token not in serialized
    assert totp_secret not in serialized
    assert all(row["correlation_id"] for row in rows)


def test_weaker_argon2_hash_is_upgraded_after_login(auth_service: AuthService) -> None:
    from argon2 import PasswordHasher

    weak = PasswordHasher(time_cost=1, memory_cost=8 * 1024, parallelism=1)
    weak_hash = weak.hash("correct horse battery staple")
    with auth_service.database.transaction() as connection:
        connection.execute("UPDATE admin_users SET password_hash = ?", (weak_hash,))

    auth_service.login(SecretStr("correct horse battery staple"), "127.0.0.1", "test")

    with auth_service.database.connect() as connection:
        upgraded = str(connection.execute("SELECT password_hash FROM admin_users").fetchone()[0])
    assert upgraded != weak_hash
    assert "correct horse battery staple" not in upgraded


def test_duplicate_bootstrap_is_audited_without_secret_values(auth_service: AuthService) -> None:
    with pytest.raises(AdminAlreadyBootstrapped):
        auth_service.bootstrap_admin(
            SecretStr("correct horse battery staple"), SecretStr(pyotp.random_base32())
        )
    with auth_service.database.connect() as connection:
        event = connection.execute(
            "SELECT event_type, metadata FROM security_events "
            "WHERE event_type = 'admin_bootstrap_rejected'"
        ).fetchone()
    assert event is not None
    assert "correct horse battery staple" not in str(event)


def test_denied_session_paths_are_audited_without_raw_tokens(tmp_path: Path) -> None:
    database = Database(tmp_path / "denied-audit.db")
    database.migrate()
    current = datetime(2026, 8, 29, tzinfo=UTC)
    service = AuthService(database, now=lambda: current)
    secret = pyotp.random_base32()
    service.bootstrap_admin(SecretStr("correct horse battery staple"), SecretStr(secret))
    tokens = service.login(SecretStr("correct horse battery staple"), "127.0.0.1", "test")
    service.revoke(tokens.session_id)

    with pytest.raises(SessionExpired):
        service.authenticate_mutation(
            tokens.cookie_token,
            tokens.csrf_token,
            ip="127.0.0.1",
            correlation_id="corr-mut",
        )
    with pytest.raises(SessionExpired):
        service.verify_totp(
            tokens.session_id,
            pyotp.TOTP(secret).now(),
            correlation_id="corr-totp",
        )
    with pytest.raises(SessionExpired):
        service.require_recent_totp(
            tokens.session_id,
            timedelta(minutes=5),
            correlation_id="corr-recent-invalid",
        )

    fresh = service.login(SecretStr("correct horse battery staple"), "127.0.0.1", "test")
    with pytest.raises(RecentTotpRequired):
        service.require_recent_totp(
            fresh.session_id,
            timedelta(minutes=5),
            correlation_id="corr-missing",
        )
    with database.transaction() as connection:
        connection.execute(
            "UPDATE admin_sessions SET last_totp_at = ? WHERE session_hash = ?",
            ((current - timedelta(minutes=10)).isoformat(), service._hash_token(fresh.session_id)),
        )
    with pytest.raises(RecentTotpRequired):
        service.require_recent_totp(
            fresh.session_id,
            timedelta(minutes=5),
            correlation_id="corr-stale",
        )
    with database.transaction() as connection:
        connection.execute(
            "UPDATE admin_sessions SET last_totp_at = ? WHERE session_hash = ?",
            ((current + timedelta(minutes=1)).isoformat(), service._hash_token(fresh.session_id)),
        )
    with pytest.raises(RecentTotpRequired):
        service.require_recent_totp(
            fresh.session_id,
            timedelta(minutes=5),
            correlation_id="corr-future",
        )

    with database.connect() as connection:
        rows = connection.execute(
            "SELECT event_type, metadata, correlation_id FROM security_events "
            "WHERE event_type IN ('mutation_auth_failed', 'totp_auth_failed', 'recent_totp_failed')"
        ).fetchall()
    assert {str(row["event_type"]) for row in rows} >= {
        "mutation_auth_failed",
        "totp_auth_failed",
        "recent_totp_failed",
    }
    serialized = json.dumps([dict(row) for row in rows], sort_keys=True)
    assert tokens.cookie_token not in serialized
    assert tokens.csrf_token not in serialized
    assert secret not in serialized
    assert all(row["correlation_id"] for row in rows)
    correlations = {str(row["correlation_id"]) for row in rows}
    assert {
        "corr-mut",
        "corr-totp",
        "corr-recent-invalid",
        "corr-missing",
        "corr-stale",
        "corr-future",
    }.issubset(correlations)
    reasons = {json.loads(str(row["metadata"]))["reason"] for row in rows}
    assert {
        "invalid_or_expired_session",
        "missing_totp",
        "stale_totp",
        "future_totp",
    }.issubset(reasons)


def test_concurrent_wrong_password_attempts_do_not_lose_failure_increments(
    auth_service: AuthService,
) -> None:
    def attempt() -> bool:
        try:
            auth_service.login(SecretStr("wrong password"), "127.0.0.1", "test")
        except (InvalidCredentials, AuthenticationThrottled):
            return False
        return True

    with ThreadPoolExecutor(max_workers=4) as pool:
        outcomes = list(
            pool.map(lambda _: attempt(), range(auth_service.password_failure_limit + 2))
        )

    assert not any(outcomes)
    with auth_service.database.connect() as connection:
        row = connection.execute(
            "SELECT failures FROM admin_auth_failures WHERE kind = 'password' AND subject = ?",
            ("127.0.0.1",),
        ).fetchone()
    assert row is not None and int(row["failures"]) >= auth_service.password_failure_limit
    with pytest.raises(AuthenticationThrottled):
        auth_service.login(SecretStr("correct horse battery staple"), "127.0.0.1", "test")
