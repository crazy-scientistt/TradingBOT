import hashlib
from typing import Any

from goldguard.providers.client import GatewayClient
from goldguard.providers.models import ModelCapability
from goldguard.storage.repositories import ProviderRepository, RouteRow


class RouteMutationError(ValueError):
    pass


class ProviderService:
    def __init__(
        self,
        provider_repo: ProviderRepository,
        gateway_client: GatewayClient,
    ) -> None:
        self.provider_repo = provider_repo
        self.gateway_client = gateway_client

    async def discover_models(self) -> list[ModelCapability]:
        return await self.gateway_client.list_models()

    def register_provider(
        self,
        *,
        name: str,
        kind: str,
        base_url: str,
        api_key: str,
        status: str = "active",
    ) -> str:
        fingerprint = hashlib.sha256(api_key.encode()).hexdigest()[:16]
        self.provider_repo.upsert_provider(
            name=name,
            kind=kind,
            base_url=base_url,
            key_fingerprint=f"sha256:{fingerprint}",
            status=status,
        )
        return fingerprint

    async def test_gateway_health(self) -> dict[str, Any]:
        return await self.gateway_client.healthz()


class RouteService:
    def __init__(self, provider_repo: ProviderRepository) -> None:
        self.provider_repo = provider_repo

    def set_route(
        self,
        *,
        role: str,
        provider: str,
        model: str,
        pinned: bool = True,
        bot_state: str = "DISARMED",
    ) -> int:
        is_live_armed = (
            bot_state in ("RUNNING_OPEN", "LIVE_READ_ONLY", "RUNNING_FLAT")
            and "live" in bot_state.lower()
        )
        if is_live_armed:
            raise RouteMutationError(
                "Cannot mutate model routes while system is armed in live mode"
            )

        # Reject openrouter/free models for decision route in production
        if role == "decision" and ("free" in model.lower() or "mock" in model.lower()):
            raise RouteMutationError("Free/mock models not permitted on primary decision route")

        return self.provider_repo.set_route(
            role=role,
            provider=provider,
            model=model,
            pinned=pinned,
        )

    def get_active_routes(self) -> dict[str, RouteRow]:
        return self.provider_repo.get_active_routes()
