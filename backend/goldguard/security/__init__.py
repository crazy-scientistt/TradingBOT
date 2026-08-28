"""Authentication and control-plane security primitives."""

from goldguard.security.models import (
    AdminAlreadyBootstrapped,
    AuthenticationError,
    AuthenticationThrottled,
    AuthPrincipal,
    AuthSession,
    CsrfValidationError,
    InvalidCredentials,
    RateLimitExceeded,
    RecentTotpRequired,
    SecurityError,
    SessionExpired,
    SessionTokens,
    TotpFailed,
    TotpRequired,
)
from goldguard.security.service import AuthService

__all__ = [
    "AdminAlreadyBootstrapped",
    "AuthPrincipal",
    "AuthService",
    "AuthSession",
    "AuthenticationError",
    "AuthenticationThrottled",
    "CsrfValidationError",
    "InvalidCredentials",
    "RateLimitExceeded",
    "RecentTotpRequired",
    "SecurityError",
    "SessionExpired",
    "SessionTokens",
    "TotpFailed",
    "TotpRequired",
]
