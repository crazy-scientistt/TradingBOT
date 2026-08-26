from pathlib import Path

import httpx
import pytest
from goldguard.providers.client import GatewayClient
from goldguard.providers.service import (
    ProviderService,
    RouteMutationError,
    RouteService,
)
from goldguard.storage.database import Database
from goldguard.storage.repositories import ProviderRepository


@pytest.fixture
def database(tmp_path: Path) -> Database:
    db = Database(tmp_path / "goldguard.db")
    db.migrate()
    return db


def test_provider_registration_is_write_only_and_fingerprinted(database: Database) -> None:
    repo = ProviderRepository(database)
    async_client = httpx.AsyncClient()
    gateway_client = GatewayClient(base_url="http://localhost:10100", http_client=async_client)
    service = ProviderService(repo, gateway_client)

    raw_key = "sk-test-super-secret-key-123456"
    fingerprint = service.register_provider(
        name="custom-openai",
        kind="openai",
        base_url="https://api.openai.com/v1",
        api_key=raw_key,
    )

    assert raw_key not in fingerprint
    with database.connect() as conn:
        query = "SELECT key_fingerprint FROM providers WHERE name = 'custom-openai'"
        row = conn.execute(query).fetchone()
        assert row is not None
        stored_fp = str(row[0])
        assert raw_key not in stored_fp
        assert "sha256:" in stored_fp


def test_route_service_guards_live_mode_and_free_models(database: Database) -> None:
    repo = ProviderRepository(database)
    repo.upsert_provider(
        name="opencodex",
        kind="opencodex",
        base_url="http://localhost:10100",
        key_fingerprint="sha256:test",
        status="active",
    )

    route_service = RouteService(repo)

    # Valid route in paper mode
    v1 = route_service.set_route(
        role="decision",
        provider="opencodex",
        model="google-antigravity/gemini-3.7-flash",
        bot_state="DISARMED",
    )
    assert v1 == 1

    # Route change blocked in live armed state
    with pytest.raises(
        RouteMutationError,
        match="Cannot mutate model routes while system is armed in live mode",
    ):
        route_service.set_route(
            role="decision",
            provider="opencodex",
            model="google-antigravity/gemini-3.7-flash",
            bot_state="LIVE_READ_ONLY",
        )

    # Free/mock models rejected for decision route
    with pytest.raises(RouteMutationError, match="Free/mock models not permitted"):
        route_service.set_route(
            role="decision",
            provider="opencodex",
            model="openrouter/free:gemini",
            bot_state="DISARMED",
        )
