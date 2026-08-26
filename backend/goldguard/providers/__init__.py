"""Pluggable AI provider gateway and model routing."""

from goldguard.providers.client import (
    AuthenticationError,
    GatewayClient,
    GatewayError,
    GatewayUnavailableError,
    RateLimitError,
)
from goldguard.providers.models import (
    ChatCompletionChoice,
    ChatCompletionRequest,
    ChatCompletionResponse,
    ChatMessage,
    ModelCapability,
    ModelRoute,
    ProviderRef,
    UsageMeta,
)
from goldguard.providers.redaction import redact_secrets, redact_string
from goldguard.providers.service import (
    ProviderService,
    RouteMutationError,
    RouteService,
)

__all__ = [
    "AuthenticationError",
    "ChatCompletionChoice",
    "ChatCompletionRequest",
    "ChatCompletionResponse",
    "ChatMessage",
    "GatewayClient",
    "GatewayError",
    "GatewayUnavailableError",
    "ModelCapability",
    "ModelRoute",
    "ProviderRef",
    "ProviderService",
    "RateLimitError",
    "RouteMutationError",
    "RouteService",
    "UsageMeta",
    "redact_secrets",
    "redact_string",
]
