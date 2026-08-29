from __future__ import annotations

import pytest
from goldguard.domain.enums import ProductKind
from goldguard.exchange.binance_transport import (
    BinanceAuthenticationError,
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
async def test_transport_without_client_fails_closed() -> None:
    transport = BinanceTransport(api_key=SecretStr("key"), api_secret=SecretStr("secret"))
    with pytest.raises(BinanceTransportError, match="TRANSPORT_CLIENT_REQUIRED"):
        await transport.request(ProductKind.SPOT, "GET", "/api/v3/time", {}, signed=False)
