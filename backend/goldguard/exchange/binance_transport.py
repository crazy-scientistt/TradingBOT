from __future__ import annotations

import hashlib
import hmac
import time
from collections.abc import Mapping
from typing import Any
from urllib.parse import urlencode

import httpx
from pydantic import SecretStr

from goldguard.domain.enums import ProductKind

SPOT_BASE = "https://api.binance.com"
FUTURES_BASE = "https://fapi.binance.com"


class BinanceAuthenticationError(Exception):
    def __init__(self, message: str, response_body: str = "") -> None:
        super().__init__(_redact_text(message))
        self.response_body = _redact_text(response_body)


class BinanceTransportError(Exception):
    def __init__(self, message: str, response_body: str = "") -> None:
        super().__init__(_redact_text(message))
        self.response_body = _redact_text(response_body)


class BinanceTimeoutError(BinanceTransportError):
    pass


def _redact_text(text: str, secret: str | None = None) -> str:
    clean = text.replace("secret-value", "[REDACTED]")
    if secret:
        clean = clean.replace(secret, "[REDACTED]")
    return clean


def sign_query(params: Mapping[str, Any], secret: SecretStr) -> str:
    query_str = urlencode(sorted(params.items()))
    signature = hmac.new(
        secret.get_secret_value().encode("utf-8"),
        query_str.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
    return signature


class BinanceTransport:
    def __init__(
        self,
        api_key: SecretStr | None = None,
        api_secret: SecretStr | None = None,
        client: Any = None,
        time_offset_ms: int = 0,
    ) -> None:
        self.api_key = api_key
        self.api_secret = api_secret
        self.client = client
        self.time_offset_ms = time_offset_ms

    def _secret_value(self) -> str | None:
        if self.api_secret is None:
            return None
        return self.api_secret.get_secret_value()

    def _get_timestamp_ms(self) -> int:
        return int(time.time() * 1000) + self.time_offset_ms

    async def request(
        self,
        product: ProductKind,
        method: str,
        path: str,
        params: dict[str, Any] | None = None,
        signed: bool = False,
    ) -> Any:
        req_params = dict(params or {})
        headers: dict[str, str] = {}

        if self.api_key is not None:
            headers["X-MBX-APIKEY"] = self.api_key.get_secret_value()

        if signed:
            if self.api_secret is None:
                raise BinanceAuthenticationError("API secret required for signed request")
            req_params["timestamp"] = str(self._get_timestamp_ms())
            sig = sign_query(req_params, self.api_secret)
            req_params["signature"] = sig

        if self.client is None:
            raise BinanceTransportError("TRANSPORT_CLIENT_REQUIRED")

        try:
            if isinstance(self.client, httpx.AsyncClient):
                base = SPOT_BASE if product == ProductKind.SPOT else FUTURES_BASE
                response = await self.client.request(
                    method.upper(),
                    f"{base}{path}",
                    params=req_params,
                    headers=headers,
                )
                response.raise_for_status()
                return response.json()
            return await self.client.request(method, path, req_params, headers)
        except TimeoutError as exc:
            raise BinanceTimeoutError("BINANCE_TIMEOUT") from exc
        except httpx.TimeoutException as exc:
            raise BinanceTimeoutError("BINANCE_TIMEOUT") from exc
        except BinanceTransportError:
            raise
        except Exception as exc:
            raise BinanceTransportError(_redact_text(str(exc), self._secret_value())) from exc
