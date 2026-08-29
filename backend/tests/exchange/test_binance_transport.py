from __future__ import annotations

import pytest
from goldguard.exchange.binance_transport import (
    BinanceAuthenticationError,
    BinanceTransport,
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

