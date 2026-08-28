from __future__ import annotations

import base64
import hashlib
import hmac
import secrets
import uuid
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING, Any

import pyotp
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError
from pydantic import SecretStr

from goldguard.security.models import (
    AdminAlreadyBootstrapped,
    AuthenticationThrottled,
    AuthPrincipal,
    AuthSession,
    CsrfValidationError,
    InvalidCredentials,
    RecentTotpRequired,
    SessionExpired,
    SessionTokens,
    TotpRequired,
)
from goldguard.storage.database import Database

if TYPE_CHECKING:
    from starlette.requests import Request


class AuthService:
    """Durable single-admin authentication and session boundary.

    Session and CSRF values are generated independently and only SHA-256 digests are
    persisted. The service intentionally exposes no database row identifier.
    """

    username = "admin"
    password_failure_limit = 5
    totp_failure_limit = 5
    failure_lockout = timedelta(minutes=5)

    def __init__(
        self,
        database: Database,
        *,
        now: Callable[[], datetime] | None = None,
        idle_timeout: timedelta = timedelta(minutes=30),
        absolute_timeout: timedelta = timedelta(hours=12),
        production: bool = False,
    ) -> None:
        if idle_timeout <= timedelta(0):
            raise ValueError("idle timeout must be positive")
        if absolute_timeout <= timedelta(0):
            raise ValueError("absolute timeout must be positive")
        if absolute_timeout < idle_timeout:
            raise ValueError("absolute timeout must not be shorter than idle timeout")
        self.database = database
        self.idle_timeout = idle_timeout
        self.absolute_timeout = absolute_timeout
        self.production = production
        self._now = now or (lambda: datetime.now(UTC))
        self._password_hasher = PasswordHasher()

    @staticmethod
    def _utc(value: datetime) -> datetime:
        if value.tzinfo is None:
            return value.replace(tzinfo=UTC)
        return value.astimezone(UTC)

    def _current_time(self) -> datetime:
        return self._utc(self._now())

    @staticmethod
    def _timestamp(value: datetime) -> str:
        return AuthService._utc(value).isoformat()

    @staticmethod
    def _parse_timestamp(value: str | None) -> datetime | None:
        if value is None:
            return None
        return AuthService._utc(datetime.fromisoformat(value))

    @staticmethod
    def _hash_token(value: str) -> str:
        return hashlib.sha256(value.encode("utf-8")).hexdigest()

    @staticmethod
    def _validate_totp_secret(secret: str) -> None:
        # pyotp accepts unpadded Base32. Decode only to reject empty/obviously invalid
        # bootstrap values while retaining compatibility with normal provisioning output.
        if not secret:
            raise ValueError("TOTP secret must not be empty")
        padded = secret.upper() + "=" * (-len(secret) % 8)
        try:
            base64.b32decode(padded, casefold=True)
        except Exception as exc:  # binascii.Error differs across Python versions
            raise ValueError("TOTP secret must be Base32") from exc

    def bootstrap_admin(self, password: SecretStr, totp_secret: SecretStr) -> None:
        password_value = password.get_secret_value()
        if len(password_value) < 12:
            raise ValueError("admin password must contain at least 12 characters")
        secret_value = totp_secret.get_secret_value()
        self._validate_totp_secret(secret_value)
        password_hash = self._password_hasher.hash(password_value)
        now = self._timestamp(self._current_time())

        with self.database.transaction() as connection:
            existing = connection.execute(
                "SELECT 1 FROM admin_users WHERE username = ?", (self.username,)
            ).fetchone()
            if existing is not None:
                raise AdminAlreadyBootstrapped("admin is already bootstrapped")
            connection.execute(
                "INSERT INTO admin_users(username, password_hash, totp_secret, created_at) "
                "VALUES (?, ?, ?, ?)",
                (self.username, password_hash, secret_value, now),
            )

    def _check_throttle(self, kind: str, subject: str, now: datetime) -> None:
        with self.database.connect() as connection:
            failure = connection.execute(
                "SELECT locked_until FROM admin_auth_failures "
                "WHERE kind = ? AND subject = ?",
                (kind, subject),
            ).fetchone()
        if failure is None:
            return
        locked_until = self._parse_timestamp(failure["locked_until"])
        if locked_until is not None and locked_until > now:
            raise AuthenticationThrottled("authentication temporarily throttled")

    def _record_failure(self, kind: str, subject: str, now: datetime, limit: int) -> None:
        now_text = self._timestamp(now)
        lock_text = self._timestamp(now + self.failure_lockout)
        with self.database.transaction() as connection:
            row = connection.execute(
                "SELECT failures FROM admin_auth_failures WHERE kind = ? AND subject = ?",
                (kind, subject),
            ).fetchone()
            failures = 1 if row is None else int(row["failures"]) + 1
            connection.execute(
                "INSERT INTO admin_auth_failures "
                "(kind, subject, failures, first_failed_at, last_failed_at, locked_until) "
                "VALUES (?, ?, ?, ?, ?, ?) "
                "ON CONFLICT(kind, subject) DO UPDATE SET failures = excluded.failures, "
                "last_failed_at = excluded.last_failed_at, locked_until = excluded.locked_until",
                (
                    kind,
                    subject,
                    failures,
                    now_text if row is None else None,
                    now_text,
                    lock_text if failures >= limit else None,
                ),
            )

    def _clear_failures(self, kind: str, subject: str) -> None:
        with self.database.transaction() as connection:
            connection.execute(
                "DELETE FROM admin_auth_failures WHERE kind = ? AND subject = ?",
                (kind, subject),
            )

    def login(self, password: SecretStr, ip: str, user_agent: str) -> SessionTokens:
        now = self._current_time()
        subject = ip or "unknown"
        self._check_throttle("password", subject, now)
        with self.database.connect() as connection:
            admin = connection.execute(
                "SELECT password_hash FROM admin_users WHERE username = ?", (self.username,)
            ).fetchone()
        valid = False
        if admin is not None:
            try:
                valid = self._password_hasher.verify(
                    str(admin["password_hash"]), password.get_secret_value()
                )
            except (InvalidHashError, VerificationError, VerifyMismatchError):
                valid = False
        if not valid:
            self._record_failure("password", subject, now, self.password_failure_limit)
            raise InvalidCredentials("invalid credentials")
        self._clear_failures("password", subject)
        return self._create_session(self.username, ip, user_agent, now)

    def _create_session(
        self,
        username: str,
        ip: str,
        user_agent: str,
        now: datetime,
        *,
        last_totp_at: datetime | None = None,
        absolute_expires_at: datetime | None = None,
    ) -> SessionTokens:
        cookie_token = secrets.token_urlsafe(32)
        csrf_token = secrets.token_urlsafe(32)
        absolute = absolute_expires_at or (now + self.absolute_timeout)
        expires = min(now + self.idle_timeout, absolute)
        with self.database.transaction() as connection:
            connection.execute(
                "INSERT INTO admin_sessions "
                "(session_hash, username, csrf_hash, expires_at, absolute_expires_at, "
                "last_seen_at, created_at, last_totp_at, ip_address, user_agent) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    self._hash_token(cookie_token),
                    username,
                    self._hash_token(csrf_token),
                    self._timestamp(expires),
                    self._timestamp(absolute),
                    self._timestamp(now),
                    self._timestamp(now),
                    None if last_totp_at is None else self._timestamp(last_totp_at),
                    ip,
                    user_agent,
                ),
            )
        return SessionTokens(cookie_token, cookie_token, csrf_token, expires)

    def _session_row(self, token: str) -> Any:
        with self.database.connect() as connection:
            return connection.execute(
                "SELECT * FROM admin_sessions WHERE session_hash = ?",
                (self._hash_token(token),),
            ).fetchone()

    def authenticate(self, session_id: str) -> AuthSession:
        if not session_id:
            raise SessionExpired("session is missing")
        now = self._current_time()
        with self.database.transaction() as connection:
            row = connection.execute(
                "SELECT * FROM admin_sessions WHERE session_hash = ?",
                (self._hash_token(session_id),),
            ).fetchone()
            if row is None:
                raise SessionExpired("session is invalid or expired")
            expires = self._parse_timestamp(str(row["expires_at"]))
            absolute = self._parse_timestamp(str(row["absolute_expires_at"]))
            if expires is None or absolute is None or now >= expires or now >= absolute:
                connection.execute(
                    "DELETE FROM admin_sessions WHERE session_hash = ?",
                    (self._hash_token(session_id),),
                )
                raise SessionExpired("session is invalid or expired")
            next_expiry = min(now + self.idle_timeout, absolute)
            connection.execute(
                "UPDATE admin_sessions SET expires_at = ?, last_seen_at = ? "
                "WHERE session_hash = ?",
                (self._timestamp(next_expiry), self._timestamp(now), self._hash_token(session_id)),
            )
            return self._auth_session_from_row(row, session_id, expires=next_expiry)

    def _auth_session_from_row(
        self,
        row: Any,
        session_id: str,
        *,
        expires: datetime | None = None,
        csrf_token: str = "",
    ) -> AuthSession:
        absolute = self._parse_timestamp(str(row["absolute_expires_at"]))
        last_totp = self._parse_timestamp(row["last_totp_at"])
        if absolute is None:
            raise SessionExpired("session is invalid or expired")
        return AuthSession(
            session_id=session_id,
            username=str(row["username"]),
            cookie_token=session_id,
            csrf_token=csrf_token,
            expires_at=expires or self._parse_timestamp(str(row["expires_at"])) or absolute,
            absolute_expires_at=absolute,
            last_totp_at=last_totp,
            ip=str(row["ip_address"]),
            user_agent=str(row["user_agent"]),
        )

    def verify_totp(self, session_id: str, code: str) -> AuthSession:
        current = self.authenticate(session_id)
        now = self._current_time()
        subject = self._hash_token(session_id)
        self._check_throttle("totp", subject, now)
        with self.database.connect() as connection:
            row = connection.execute(
                "SELECT totp_secret FROM admin_users WHERE username = ?",
                (current.username,),
            ).fetchone()
        valid = False
        if row is not None:
            try:
                valid = pyotp.TOTP(str(row["totp_secret"])).verify(
                    code,
                    for_time=now,
                    valid_window=0,
                )
            except (TypeError, ValueError):
                valid = False
        if not valid:
            self._record_failure("totp", subject, now, self.totp_failure_limit)
            with self.database.transaction() as connection:
                connection.execute(
                    "UPDATE admin_sessions SET totp_failures = totp_failures + 1, "
                    "totp_locked_until = CASE WHEN totp_failures + 1 >= ? THEN ? ELSE NULL END "
                    "WHERE session_hash = ?",
                    (self.totp_failure_limit, self._timestamp(now + self.failure_lockout), subject),
                )
            raise TotpRequired("valid TOTP is required")

        self._clear_failures("totp", subject)
        with self.database.transaction() as connection:
            old = connection.execute(
                "SELECT * FROM admin_sessions WHERE session_hash = ?",
                (subject,),
            ).fetchone()
            if old is None:
                raise SessionExpired("session is invalid or expired")
            absolute = self._parse_timestamp(str(old["absolute_expires_at"]))
            if absolute is None or now >= absolute:
                connection.execute("DELETE FROM admin_sessions WHERE session_hash = ?", (subject,))
                raise SessionExpired("session is invalid or expired")
            new_cookie = secrets.token_urlsafe(32)
            new_csrf = secrets.token_urlsafe(32)
            new_expires = min(now + self.idle_timeout, absolute)
            connection.execute("DELETE FROM admin_sessions WHERE session_hash = ?", (subject,))
            connection.execute(
                "INSERT INTO admin_sessions "
                "(session_hash, username, csrf_hash, expires_at, absolute_expires_at, "
                "last_seen_at, created_at, last_totp_at, ip_address, user_agent, "
                "totp_failures, totp_locked_until) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0, NULL)",
                (
                    self._hash_token(new_cookie),
                    str(old["username"]),
                    self._hash_token(new_csrf),
                    self._timestamp(new_expires),
                    self._timestamp(absolute),
                    self._timestamp(now),
                    str(old["created_at"]),
                    self._timestamp(now),
                    str(old["ip_address"]),
                    str(old["user_agent"]),
                ),
            )
            new_row = connection.execute(
                "SELECT * FROM admin_sessions WHERE session_hash = ?",
                (self._hash_token(new_cookie),),
            ).fetchone()
        if new_row is None:
            raise RuntimeError("rotated session was not persisted")
        return self._auth_session_from_row(
            new_row, new_cookie, expires=new_expires, csrf_token=new_csrf
        )

    def require_recent_totp(self, session_id: str, max_age: timedelta) -> None:
        if max_age < timedelta(0):
            raise ValueError("max_age must not be negative")
        session = self.authenticate(session_id)
        if session.last_totp_at is None:
            raise RecentTotpRequired("recent TOTP verification is required")
        age = self._current_time() - session.last_totp_at
        if age < timedelta(0) or age > max_age:
            raise RecentTotpRequired("recent TOTP verification is required")

    def authenticate_mutation(
        self,
        session_cookie: str | None,
        csrf_header: str | None,
        request: Request | None = None,
        *,
        ip: str | None = None,
        user_agent: str | None = None,
        correlation_id: str | None = None,
    ) -> AuthPrincipal:
        if request is not None:
            client = getattr(request, "client", None)
            ip = ip or (None if client is None else client.host)
            headers = getattr(request, "headers", {})
            user_agent = user_agent or headers.get("user-agent", "")
            correlation_id = correlation_id or headers.get("x-correlation-id")
        if not session_cookie or not csrf_header:
            raise CsrfValidationError("session cookie and CSRF token are required")
        session = self.authenticate(session_cookie)
        row = self._session_row(session_cookie)
        if row is None or not hmac.compare_digest(
            str(row["csrf_hash"]), self._hash_token(csrf_header)
        ):
            raise CsrfValidationError("CSRF token is invalid")
        return AuthPrincipal(
            username=session.username,
            session_id=session.session_id,
            ip=session.ip,
            user_agent=session.user_agent,
            last_totp_at=session.last_totp_at,
            correlation_id=correlation_id or uuid.uuid4().hex,
        )

    def revoke(self, session_id: str) -> None:
        with self.database.transaction() as connection:
            connection.execute(
                "DELETE FROM admin_sessions WHERE session_hash = ?",
                (self._hash_token(session_id),),
            )
