from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime


class SecurityError(Exception):
    """Base class for expected security boundary failures."""


class AdminAlreadyBootstrapped(SecurityError):
    pass


class AuthenticationError(SecurityError):
    pass


class InvalidCredentials(AuthenticationError):
    pass


class AuthenticationThrottled(AuthenticationError):
    pass


class SessionExpired(AuthenticationError):
    pass


class TotpRequired(AuthenticationError):
    pass


class TotpReplayRejected(TotpRequired):
    pass


# Descriptive aliases kept for callers that use failure-oriented terminology.
TotpFailed = TotpRequired
RateLimitExceeded = AuthenticationThrottled


class RecentTotpRequired(AuthenticationError):
    pass


class CsrfValidationError(AuthenticationError):
    pass


@dataclass(frozen=True, slots=True)
class SessionTokens:
    """Opaque values returned to the browser; raw values are never persisted."""

    session_id: str = field(repr=False)
    cookie_token: str = field(repr=False)
    csrf_token: str = field(repr=False)
    expires_at: datetime
    absolute_expires_at: datetime | None = None

    def __repr__(self) -> str:
        return f"SessionTokens(expires_at={self.expires_at!r})"


@dataclass(frozen=True, slots=True)
class AuthSession:
    """Authenticated session state, with rotated opaque tokens when applicable."""

    session_id: str = field(repr=False)
    username: str
    cookie_token: str = field(repr=False)
    csrf_token: str = field(repr=False)
    expires_at: datetime
    absolute_expires_at: datetime
    last_totp_at: datetime | None
    ip: str
    user_agent: str

    def __repr__(self) -> str:
        return (
            "AuthSession("
            f"username={self.username!r}, expires_at={self.expires_at!r}, "
            f"absolute_expires_at={self.absolute_expires_at!r}, last_totp_at={self.last_totp_at!r}"
            ")"
        )

    @property
    def totp_verified_at(self) -> datetime | None:
        return self.last_totp_at


@dataclass(frozen=True, slots=True)
class AuthPrincipal:
    username: str
    session_id: str = field(repr=False)
    ip: str
    user_agent: str
    last_totp_at: datetime | None
    correlation_id: str = field(default="", repr=False)

    @property
    def actor(self) -> str:
        """Stable audit actor alias consumed by later control-plane routes."""

        return self.username

    def __repr__(self) -> str:
        return f"AuthPrincipal(username={self.username!r}, ip={self.ip!r})"
