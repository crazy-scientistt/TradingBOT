import httpx
import pytest
from goldguard.providers.client import (
    AuthenticationError,
    GatewayClient,
    RateLimitError,
)
from goldguard.providers.models import ChatCompletionRequest, ChatMessage
from goldguard.providers.redaction import redact_secrets, redact_string


@pytest.mark.asyncio
async def test_gateway_client_sends_opencodex_and_bearer_headers() -> None:
    seen: dict[str, str] = {}

    async def mock_health(request: httpx.Request) -> httpx.Response:
        seen.update({k.lower(): v for k, v in request.headers.items()})
        return httpx.Response(200, json={"status": "ok"})

    transport = httpx.MockTransport(mock_health)
    async with httpx.AsyncClient(transport=transport) as http_client:
        client = GatewayClient(
            base_url="http://gateway:10100",
            auth_token="railway-token",
            http_client=http_client,
        )
        await client.healthz()

    assert seen.get("x-opencodex-api-key") == "railway-token"
    assert seen.get("authorization") == "Bearer railway-token"


@pytest.mark.asyncio
async def test_gateway_client_chat_completion_success() -> None:
    async def mock_handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/v1/chat/completions":
            return httpx.Response(
                200,
                json={
                    "id": "chat-123",
                    "model": "google-antigravity/gemini-3.7-flash",
                    "choices": [
                        {
                            "index": 0,
                            "message": {
                                "role": "assistant",
                                "content": '{"decision":"APPROVE_ENTRY"}',
                            },
                            "finish_reason": "stop",
                        }
                    ],
                    "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
                },
            )
        return httpx.Response(404)

    transport = httpx.MockTransport(mock_handler)
    async with httpx.AsyncClient(transport=transport) as http_client:
        client = GatewayClient(base_url="http://gateway:10100", http_client=http_client)
        req = ChatCompletionRequest(
            model="google-antigravity/gemini-3.7-flash",
            messages=[ChatMessage(role="user", content="evaluate setup")],
        )
        resp = await client.chat_completion(req)
        assert resp.id == "chat-123"
        assert resp.content == '{"decision":"APPROVE_ENTRY"}'
        assert resp.usage is not None
        assert resp.usage.total_tokens == 15


@pytest.mark.asyncio
async def test_gateway_client_maps_auth_and_rate_limit_errors() -> None:
    async def mock_auth_fail(request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, json={"error": "invalid token sk-1234567890abcdef"})

    async def mock_rate_limit(request: httpx.Request) -> httpx.Response:
        return httpx.Response(429, json={"error": "rate limited"})

    # 401 Auth Error with secret redaction
    transport_auth = httpx.MockTransport(mock_auth_fail)
    async with httpx.AsyncClient(transport=transport_auth) as http_client:
        client = GatewayClient(base_url="http://gateway:10100", http_client=http_client)
        with pytest.raises(AuthenticationError):
            await client.healthz()

    # 429 Rate Limit
    transport_rl = httpx.MockTransport(mock_rate_limit)
    async with httpx.AsyncClient(transport=transport_rl) as http_client:
        client = GatewayClient(base_url="http://gateway:10100", http_client=http_client)
        with pytest.raises(RateLimitError):
            await client.list_models()


@pytest.mark.asyncio
async def test_gateway_client_parses_model_catalog() -> None:
    async def mock_models(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "data": [
                    {"id": "google-antigravity/gemini-3.7-flash", "name": "Gemini 3.7 Flash"},
                    {"id": "google-antigravity/gemini-3.7-flash", "name": "Duplicate Entry"},
                    {"id": "trade/claude-opus-5", "name": "Claude Opus 5"},
                ]
            },
        )

    transport = httpx.MockTransport(mock_models)
    async with httpx.AsyncClient(transport=transport) as http_client:
        client = GatewayClient(base_url="http://gateway:10100", http_client=http_client)
        models = await client.list_models()
        assert len(models) == 2
        assert models[0].model_id == "google-antigravity/gemini-3.7-flash"
        assert models[0].web_search is True


def test_secret_redaction_scrubs_keys_in_all_structures() -> None:
    raw_str = "Error with key sk-abcdef1234567890 and Bearer eyJhbGciOiJIUzI1NiJ9"
    redacted = redact_string(raw_str)
    assert "sk-abcdef1234567890" not in redacted
    assert "[REDACTED]" in redacted

    raw_dict = {
        "user": "alice",
        "api_key": "secret-key-12345",
        "nested": {"token": "Bearer abcdefgh12345678", "normal": "hello"},
    }
    cleaned = redact_secrets(raw_dict)
    assert cleaned["api_key"] == "[REDACTED]"
    assert cleaned["nested"]["token"] == "[REDACTED]"
    assert cleaned["nested"]["normal"] == "hello"
