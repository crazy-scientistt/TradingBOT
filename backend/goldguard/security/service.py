from __future__ import annotations

import base64
import hashlib
import hmac
import json
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
    TotpReplayRejected,
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
    argon2_time_cost = 3
    argon2_memory_cost = 64 * 1024
    argon2_parallelism = 4
    argon2_hash_len = 32
    argon2_salt_len = 16

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
        self._password_hasher = PasswordHasher(
            time_cost=self.argon2_time_cost,
            memory_cost=self.argon2_memory_cost,
            parallelism=self.argon2_parallelism,
            hash_len=self.argon2_hash_len,
            salt_len=self.argon2_salt_len,
        )

    @staticmethod
    def _utc(value: datetime) -> datetime:
        if value.tzinfo is None:
            return value.replace(tzinfo=UTC)
        return value.astimezone(UTC)

    def _current_time(self) -> datetime:
        return self._utc(self._now())

    def current_time(self) -> datetime:
        """Return the injected UTC clock used for session/cookie expiry."""

        return self._current_time()

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

    def _audit(
        self,
        connection: Any,
        event_type: str,
        *,
        actor: str | None,
        ip: str | None,
        user_agent: str | None,
        correlation_id: str,
        outcome: str,
        metadata: dict[str, object] | None = None,
    ) -> None:
        details = dict(metadata or {})
        details["outcome"] = outcome
        connection.execute(
            "INSERT INTO security_events "
            "(event_type, actor, ip_address, user_agent, correlation_id, metadata, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                event_type,
                actor,
                ip,
                user_agent,
                correlation_id,
                json.dumps(details, separators=(",", ":"), sort_keys=True),
                self._timestamp(self._current_time()),
            ),
        )

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
        correlation = uuid.uuid4().hex
        duplicate = False

        with self.database.transaction() as connection:
            existing = connection.execute(
                "SELECT 1 FROM admin_users WHERE username = ?", (self.username,)
            ).fetchone()
            if existing is not None:
                duplicate = True
                self._audit(
                    connection,
                    "admin_bootstrap_rejected",
                    actor=self.username,
                    ip=None,
                    user_agent=None,
                    correlation_id=correlation,
                    outcome="rejected",
                )
            else:
                connection.execute(
                    "INSERT INTO admin_users(username, password_hash, totp_secret, created_at) "
                    "VALUES (?, ?, ?, ?)",
                    (self.username, password_hash, secret_value, now),
                )
                self._audit(
                    connection,
                    "admin_bootstrapped",
                    actor=self.username,
                    ip=None,
                    user_agent=None,
                    correlation_id=correlation,
                    outcome="success",
                )
        if duplicate:
            raise AdminAlreadyBootstrapped("admin is already bootstrapped")

    def _check_throttle(
        self,
        kind: str,
        subject: str,
        now: datetime,
        *,
        ip: str | None,
        user_agent: str | None,
        correlation_id: str,
    ) -> None:
        blocked = False
        with self.database.transaction() as connection:
            failure = connection.execute(
                "SELECT locked_until FROM admin_auth_failures "
                "WHERE kind = ? AND subject = ?",
                (kind, subject),
            ).fetchone()
            if failure is not None:
                locked_until = self._parse_timestamp(failure["locked_until"])
                blocked = locked_until is not None and locked_until > now
            if blocked:
                self._audit(
                    connection,
                    "login_throttled" if kind == "password" else "totp_throttled",
                    actor=self.username,
                    ip=ip,
                    user_agent=user_agent,
                    correlation_id=correlation_id,
                    outcome="throttled",
                )
        if blocked:
            raise AuthenticationThrottled("authentication temporarily throttled")

    def _record_failure(
        self,
        kind: str,
        subject: str,
        now: datetime,
        limit: int,
        *,
        ip: str | None,
        user_agent: str | None,
        correlation_id: str,
    ) -> None:
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
            self._audit(
                connection,
                "login_failed" if kind == "password" else "totp_failed",
                actor=self.username,
                ip=ip,
                user_agent=user_agent,
                correlation_id=correlation_id,
                outcome="failure",
                metadata={"failure_count": failures, "throttled": failures >= limit},
            )

    def _clear_failures(self, kind: str, subject: str, now: datetime) -> None:
        with self.database.transaction() as connection:
            connection.execute(
                "DELETE FROM admin_auth_failures WHERE kind = ? AND subject = ? "
                "AND (locked_until IS NULL OR locked_until <= ?)",
                (kind, subject, self._timestamp(now)),
            )

    def login(
        self,
        password: SecretStr,
        ip: str,
        user_agent: str,
        *,
        correlation_id: str | None = None,
    ) -> SessionTokens:
        now = self._current_time()
        correlation = correlation_id or uuid.uuid4().hex
        subject = ip or "unknown"
        self._check_throttle(
            "password",
            subject,
            now,
            ip=ip,
            user_agent=user_agent,
            correlation_id=correlation,
        )
        with self.database.connect() as connection:
            admin = connection.execute(
                "SELECT password_hash FROM admin_users WHERE username = ?",
                (self.username,),
            ).fetchone()
        valid = False
        password_hash = None if admin is None else str(admin["password_hash"])
        if admin is not None:
            try:
                valid = self._password_hasher.verify(
                    password_hash or "", password.get_secret_value()
                )
            except (InvalidHashError, VerificationError, VerifyMismatchError):
                valid = False
        if not valid:
            self._record_failure(
                "password",
                subject,
                now,
                self.password_failure_limit,
                ip=ip,
                user_agent=user_agent,
                correlation_id=correlation,
            )
            raise InvalidCredentials("invalid credentials")
        if password_hash is not None and self._password_hasher.check_needs_rehash(password_hash):
            upgraded_hash = self._password_hasher.hash(password.get_secret_value())
            with self.database.transaction() as connection:
                connection.execute(
                    "UPDATE admin_users SET password_hash = ? "
                    "WHERE username = ? AND password_hash = ?",
                    (upgraded_hash, self.username, password_hash),
                )
        self._clear_failures("password", subject, now)
        return self._create_session(
            self.username,
            ip,
            user_agent,
            now,
            correlation_id=correlation,
            event_type="login_succeeded",
        )

    def _create_session(
        self,
        username: str,
        ip: str,
        user_agent: str,
        now: datetime,
        *,
        last_totp_at: datetime | None = None,
        absolute_expires_at: datetime | None = None,
        correlation_id: str | None = None,
        event_type: str | None = None,
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
            if event_type is not None:
                self._audit(
                    connection,
                    event_type,
                    actor=username,
                    ip=ip,
                    user_agent=user_agent,
                    correlation_id=correlation_id or uuid.uuid4().hex,
                    outcome="success",
                )
        return SessionTokens(cookie_token, cookie_token, csrf_token, expires, absolute)

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
        correlation = uuid.uuid4().hex
        subject = self.username
        self._check_throttle(
            "totp",
            subject,
            now,
            ip=current.ip,
            user_agent=current.user_agent,
            correlation_id=correlation,
        )
        with self.database.connect() as connection:
            row = connection.execute(
                "SELECT totp_secret, last_totp_step FROM admin_users WHERE username = ?",
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
            self._record_failure(
                "totp",
                subject,
                now,
                self.totp_failure_limit,
                ip=current.ip,
                user_agent=current.user_agent,
                correlation_id=correlation,
            )
            raise TotpRequired("valid TOTP is required")

        totp = pyotp.TOTP(str(row["totp_secret"])) if row is not None else None
        step = int(now.timestamp()) // (totp.interval if totp is not None else 30)
        replay = False
        with self.database.transaction() as connection:
            old = connection.execute(
                "SELECT * FROM admin_sessions WHERE session_hash = ?",
                (self._hash_token(session_id),),
            ).fetchone()
            if old is None:
                raise SessionExpired("session is invalid or expired")
            absolute = self._parse_timestamp(str(old["absolute_expires_at"]))
            if absolute is None or now >= absolute:
                connection.execute(
                    "DELETE FROM admin_sessions WHERE session_hash = ?",
                    (self._hash_token(session_id),),
                )
                raise SessionExpired("session is invalid or expired")
            admin = connection.execute(
                "SELECT last_totp_step FROM admin_users WHERE username = ?",
                (current.username,),
            ).fetchone()
            previous_step = None if admin is None else admin["last_totp_step"]
            if previous_step is not None and int(previous_step) >= step:
                replay = True
                self._audit(
                    connection,
                    "totp_replay",
                    actor=current.username,
                    ip=current.ip,
                    user_agent=current.user_agent,
                    correlation_id=correlation,
                    outcome="rejected",
                    metadata={"timestep": step},
                )
            else:
                updated = connection.execute(
                    "UPDATE admin_users SET last_totp_step = ? WHERE username = ? "
                    "AND (last_totp_step IS NULL OR last_totp_step < ?)",
                    (step, current.username, step),
                )
                replay = updated.rowcount != 1
            if replay:
                new_row = None
            else:
                new_cookie = secrets.token_urlsafe(32)
                new_csrf = secrets.token_urlsafe(32)
                new_expires = min(now + self.idle_timeout, absolute)
                connection.execute(
                    "DELETE FROM admin_sessions WHERE session_hash = ?",
                    (self._hash_token(session_id),),
                )
                connection.execute(
                    "INSERT INTO admin_sessions "
                    "(session_hash, username, csrf_hash, expires_at, absolute_expires_at, "
                    "last_seen_at, created_at, last_totp_at, ip_address, user_agent) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
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
                self._audit(
                    connection,
                    "totp_succeeded",
                    actor=current.username,
                    ip=current.ip,
                    user_agent=current.user_agent,
                    correlation_id=correlation,
                    outcome="success",
                    metadata={"timestep": step, "session_rotated": True},
                )
                new_row = connection.execute(
                    "SELECT * FROM admin_sessions WHERE session_hash = ?",
                    (self._hash_token(new_cookie),),
                ).fetchone()
        if replay:
            raise TotpReplayRejected("TOTP code was already accepted")
        self._clear_failures("totp", subject, now)
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
        correlation = correlation_id or uuid.uuid4().hex
        if not session_cookie:
            with self.database.transaction() as connection:
                self._audit(
                    connection,
                    "mutation_auth_failed",
                    actor=None,
                    ip=ip,
                    user_agent=user_agent,
                    correlation_id=correlation,
                    outcome="failure",
                    metadata={"reason": "missing_session"},
                )
            raise SessionExpired("session is missing")
        if not csrf_header:
            with self.database.transaction() as connection:
                self._audit(
                    connection,
                    "mutation_auth_failed",
                    actor=None,
                    ip=ip,
                    user_agent=user_agent,
                    correlation_id=correlation,
                    outcome="failure",
                    metadata={"reason": "missing_csrf"},
                )
            raise CsrfValidationError("CSRF token is required")
        session = self.authenticate(session_cookie)
        row = self._session_row(session_cookie)
        if row is None or not hmac.compare_digest(
            str(row["csrf_hash"]), self._hash_token(csrf_header)
        ):
            with self.database.transaction() as connection:
                self._audit(
                    connection,
                    "mutation_auth_failed",
                    actor=session.username,
                    ip=ip or session.ip,
                    user_agent=user_agent or session.user_agent,
                    correlation_id=correlation,
                    outcome="failure",
                    metadata={"reason": "invalid_csrf"},
                )
            raise CsrfValidationError("CSRF token is invalid")
        with self.database.transaction() as connection:
            self._audit(
                connection,
                "mutation_authenticated",
                actor=session.username,
                ip=ip or session.ip,
                user_agent=user_agent or session.user_agent,
                correlation_id=correlation,
                outcome="success",
            )
        return AuthPrincipal(
            username=session.username,
            session_id=session.session_id,
            ip=session.ip,
            user_agent=session.user_agent,
            last_totp_at=session.last_totp_at,
            correlation_id=correlation,
        )

    def revoke(self, session_id: str) -> None:
        with self.database.transaction() as connection:
            row = connection.execute(
                "SELECT username, ip_address, user_agent FROM admin_sessions "
                "WHERE session_hash = ?",
                (self._hash_token(session_id),),
            ).fetchone()
            connection.execute(
                "DELETE FROM admin_sessions WHERE session_hash = ?",
                (self._hash_token(session_id),),
            )
            self._audit(
                connection,
                "session_revoked",
                actor=None if row is None else str(row["username"]),
                ip=None if row is None else str(row["ip_address"]),
                user_agent=None if row is None else str(row["user_agent"]),
                correlation_id=uuid.uuid4().hex,
                outcome="success" if row is not None else "not_found",
                metadata={"revoked": row is not None},
            )
