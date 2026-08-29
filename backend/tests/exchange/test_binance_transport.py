from __future__ import annotations

import httpx
import pytest
from goldguard.domain.enums import ProductKind
from goldguard.exchange.binance_transport import (
    BinanceAuthenticationError,
    BinanceTimeoutError,
    BinanceTransport,
    BinanceTransportError,
    sign_query,
)
from pydantic import SecretStr


@pytest.mark.asyncio
async def test_signed_request_uses_signature() -> None:
    secret = SecretStr("mock-binance-secret")
    _ = BinanceTransport(
        api_key=SecretStr("mock-api-key"),
        api_secret=secret,
    )
    sig = sign_query({"symbol": "BTCUSDT", "timestamp": "1724832000123"}, secret)
    assert len(sig) == 64


def test_transport_error_redacts_api_secret() -> None:
    error = BinanceAuthenticationError("secret-value", response_body="secret-value")
    assert "secret-value" not in str(error)
    assert "secret-value" not in error.response_body


@pytest.mark.asyncio
async def test_transport_without_client_is_fail_closed() -> None:
    transport = BinanceTransport(
        api_key=SecretStr("key"),
        api_secret=SecretStr("secret"),
    )
    with pytest.raises(BinanceTransportError, match="TRANSPORT_CLIENT_REQUIRED"):
        await transport.request(ProductKind.SPOT, "GET", "/api/v3/time", {}, signed=False)


@pytest.mark.asyncio
async def test_httpx_client_is_signed_and_timeout_mapped() -> None:
    secret = SecretStr("mock-binance-secret")

    async def handler(request: httpx.Request) -> httpx.Response:
        assert "signature=" in str(request.url)
        assert "timestamp=" in str(request.url)
        return httpx.Response(200, json={"serverTime": 1724832000123})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        transport = BinanceTransport(
            api_key=SecretStr("mock-api-key"),
            api_secret=secret,
            client=client,
        )
        payload = await transport.request(
            ProductKind.SPOT, "GET", "/api/v3/time", {}, signed=True
        )
        assert payload["serverTime"] == 1724832000123

    async def timeout_handler(request: httpx.Request) -> httpx.Response:
        raise httpx.TimeoutException("slow")

    async with httpx.AsyncClient(transport=httpx.MockTransport(timeout_handler)) as client:
        transport = BinanceTransport(
            api_key=SecretStr("mock-api-key"),
            api_secret=secret,
            client=client,
        )
        with pytest.raises(BinanceTimeoutError):
            await transport.request(ProductKind.SPOT, "GET", "/api/v3/time", {}, signed=True)
