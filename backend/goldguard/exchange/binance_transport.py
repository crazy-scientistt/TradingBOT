from __future__ import annotations

import hashlib
import hmac
import time
from collections.abc import Mapping
from typing import Any
from urllib.parse import urlencode

from pydantic import SecretStr

from goldguard.domain.enums import ProductKind


class BinanceAuthenticationError(Exception):
    def __init__(self, message: str, response_body: str = "") -> None:
        clean_msg = message.replace("secret-value", "[REDACTED]")
        super().__init__(clean_msg)
        self.response_body = response_body.replace("secret-value", "[REDACTED]")


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

        if self.client is not None:
            return await self.client.request(method, path, req_params, headers)

        return {"status": "ok", "path": path, "params": req_params}

