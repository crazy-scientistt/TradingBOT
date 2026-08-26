from typing import Any

import httpx
from pydantic import ValidationError

from goldguard.providers.models import (
    ChatCompletionRequest,
    ChatCompletionResponse,
    ModelCapability,
)
from goldguard.providers.redaction import redact_string


class GatewayError(RuntimeError):
    pass


class AuthenticationError(GatewayError):
    pass


class RateLimitError(GatewayError):
    pass


class GatewayUnavailableError(GatewayError):
    pass


class GatewayClient:
    """Client for OpenCodex unified AI gateway."""

    def __init__(
        self,
        *,
        base_url: str,
        auth_token: str | None = None,
        http_client: httpx.AsyncClient,
        timeout: float = 30.0,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.auth_token = auth_token
        self.http_client = http_client
        self.timeout = timeout

    def _headers(self) -> dict[str, str]:
        headers = {"content-type": "application/json"}
        if self.auth_token:
            headers["authorization"] = f"Bearer {self.auth_token}"
        return headers

    async def healthz(self) -> dict[str, Any]:
        try:
            response = await self.http_client.get(
                f"{self.base_url}/healthz",
                headers=self._headers(),
                timeout=5.0,
            )
            response.raise_for_status()
            data = response.json()
            return data if isinstance(data, dict) else {"status": "ok"}
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code in (401, 403):
                raise AuthenticationError("Gateway authentication failed") from exc
            status = exc.response.status_code
            raise GatewayUnavailableError(f"Gateway health check failed: {status}") from exc
        except (httpx.TimeoutException, httpx.NetworkError) as exc:
            msg = redact_string(str(exc))
            raise GatewayUnavailableError(f"Gateway unreachable: {msg}") from exc

    async def list_models(self) -> list[ModelCapability]:
        try:
            response = await self.http_client.get(
                f"{self.base_url}/v1/models",
                headers=self._headers(),
                timeout=10.0,
            )
            response.raise_for_status()
            data = response.json()
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code in (401, 403):
                raise AuthenticationError("Gateway authentication failed") from exc
            if exc.response.status_code == 429:
                raise RateLimitError("Gateway rate limit exceeded") from exc
            raise GatewayUnavailableError(f"Gateway error: {exc.response.status_code}") from exc
        except (httpx.TimeoutException, httpx.NetworkError) as exc:
            msg = redact_string(str(exc))
            raise GatewayUnavailableError(f"Gateway unreachable: {msg}") from exc

        raw_list = data.get("data", []) if isinstance(data, dict) else []
        models: list[ModelCapability] = []
        seen: set[str] = set()

        for item in raw_list:
            if not isinstance(item, dict):
                continue
            model_id = str(item.get("id", ""))
            if not model_id or model_id in seen:
                continue
            seen.add(model_id)

            has_search = "gemini" in model_id.lower() or "sonar" in model_id.lower()
            models.append(
                ModelCapability(
                    model_id=model_id,
                    display_name=str(item.get("name", model_id)),
                    structured_output=True,
                    web_search=has_search,
                    context_window=int(item.get("context_window", 128000)),
                )
            )
        return models

    async def chat_completion(
        self,
        request: ChatCompletionRequest,
    ) -> ChatCompletionResponse:
        payload = request.model_dump(mode="json", exclude_none=True)
        try:
            response = await self.http_client.post(
                f"{self.base_url}/v1/chat/completions",
                headers=self._headers(),
                json=payload,
                timeout=self.timeout,
            )
            response.raise_for_status()
            data = response.json()
            return ChatCompletionResponse.model_validate(data)
        except httpx.HTTPStatusError as exc:
            status = exc.response.status_code
            if status in (401, 403):
                raise AuthenticationError("Gateway authentication rejected") from exc
            if status == 429:
                raise RateLimitError("Gateway rate limit exceeded") from exc
            redacted_body = redact_string(exc.response.text)
            raise GatewayError(f"Gateway returned HTTP {status}: {redacted_body}") from exc
        except ValidationError as exc:
            msg = redact_string(str(exc))
            raise GatewayError(f"Malformed gateway response: {msg}") from exc
        except (httpx.TimeoutException, httpx.NetworkError) as exc:
            msg = redact_string(str(exc))
            raise GatewayUnavailableError(f"Gateway unreachable: {msg}") from exc
