import json

import httpx

from goldguard.hermes.models import SanitizedResearchPacket


class HermesUnavailable(RuntimeError):
    """Hermes failed safely without affecting the active trading path."""


class HermesClient:
    def __init__(
        self,
        *,
        base_url: str,
        api_key: str,
        http_client: httpx.AsyncClient,
        maximum_response_bytes: int = 16_384,
    ) -> None:
        if not api_key:
            raise ValueError("Hermes bridge key is required")
        self._base_url = base_url.rstrip("/")
        self._api_key = api_key
        self._http_client = http_client
        self._maximum_response_bytes = maximum_response_bytes

    async def request_proposal(self, packet: SanitizedResearchPacket) -> bytes:
        payload = {
            "model": "hermes-agent",
            "temperature": 0,
            "messages": [
                {
                    "role": "system",
                    "content": (
                        "Return one declarative strategy proposal as strict JSON. "
                        "Change exactly one allowed parameter and cite supplied evidence IDs."
                    ),
                },
                {
                    "role": "user",
                    "content": packet.model_dump_json(),
                },
            ],
        }
        try:
            response = await self._http_client.post(
                f"{self._base_url}/v1/chat/completions",
                headers={
                    "authorization": f"Bearer {self._api_key}",
                    "content-type": "application/json",
                },
                json=payload,
                timeout=30,
            )
            response.raise_for_status()
            content = response.json()["choices"][0]["message"]["content"]
        except (
            httpx.TimeoutException,
            httpx.NetworkError,
            httpx.HTTPStatusError,
            KeyError,
            IndexError,
            TypeError,
            ValueError,
            json.JSONDecodeError,
        ) as error:
            raise HermesUnavailable("Hermes proposal request failed closed") from error
        if not isinstance(content, str):
            raise HermesUnavailable("Hermes returned a non-text proposal")
        encoded = content.encode()
        if len(encoded) > self._maximum_response_bytes:
            raise HermesUnavailable("Hermes proposal exceeded the response limit")
        return encoded

    async def complete(self, user_content: str) -> str:
        raw = await self.request_proposal_text(user_content)
        return raw

    async def request_proposal_text(self, user_content: str) -> str:
        payload = {
            "model": "hermes-agent",
            "temperature": 0,
            "messages": [
                {
                    "role": "system",
                    "content": (
                        "Return one declarative strategy proposal as strict JSON. "
                        "Change at most two allowed parameters and cite supplied evidence IDs."
                    ),
                },
                {"role": "user", "content": user_content},
            ],
        }
        try:
            response = await self._http_client.post(
                f"{self._base_url}/v1/chat/completions",
                headers={
                    "authorization": f"Bearer {self._api_key}",
                    "content-type": "application/json",
                },
                json=payload,
                timeout=45,
            )
            response.raise_for_status()
            content = response.json()["choices"][0]["message"]["content"]
        except (
            httpx.TimeoutException,
            httpx.NetworkError,
            httpx.HTTPStatusError,
            KeyError,
            IndexError,
            TypeError,
            ValueError,
            json.JSONDecodeError,
        ) as error:
            raise HermesUnavailable("Hermes proposal request failed closed") from error
        if not isinstance(content, str) or not content.strip():
            raise HermesUnavailable("Hermes returned a non-text proposal")
        encoded = content.encode()
        if len(encoded) > self._maximum_response_bytes:
            raise HermesUnavailable("Hermes proposal exceeded the response limit")
        return content
