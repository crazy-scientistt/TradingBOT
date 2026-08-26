import sqlite3
from decimal import Decimal

import pytest
from goldguard.storage.database import Database
from goldguard.storage.repositories import (
    GenomeRepository,
    LedgerRepository,
    ProviderRepository,
    QuotaRepository,
)
from goldguard.strategy.genome import trend_pullback_v1


@pytest.fixture
def database(tmp_path) -> Database:
    db = Database(tmp_path / "goldguard.db")
    db.migrate()
    return db


@pytest.fixture
def repository(database: Database) -> LedgerRepository:
    return LedgerRepository(database)


def test_new_paper_balance_creates_a_session_without_deleting_history(
    repository: LedgerRepository,
) -> None:
    first = repository.create_paper_session(Decimal("100"))
    second = repository.create_paper_session(Decimal("250.50"))

    assert first != second
    assert repository.current_paper_session_id() == second
    sessions = repository.list_paper_sessions()
    assert [row.initial_balance for row in sessions] == [Decimal("100"), Decimal("250.50")]


def test_settings_versions_are_immutable(repository: LedgerRepository) -> None:
    identifier = repository.save_settings_version(
        version="safe-default-v1",
        payload={"risk_per_trade": "0.005"},
    )

    with (
        pytest.raises(sqlite3.IntegrityError, match="settings versions are immutable"),
        repository.database.transaction() as connection,
    ):
        connection.execute(
            "UPDATE settings_versions SET payload_json = '{}' WHERE id = ?",
            (identifier,),
        )


def test_decision_chain_is_idempotent_per_closed_candle(repository: LedgerRepository) -> None:
    session_id = repository.create_paper_session(Decimal("100"))
    key = repository.record_decision_chain(
        mode="paper",
        account_scope=session_id,
        symbol="PAXGUSDT",
        timeframe="15m",
        candle_close_time="2026-08-26T00:15:00+00:00",
    )

    assert (
        repository.record_decision_chain(
            mode="paper",
            account_scope=session_id,
            symbol="PAXGUSDT",
            timeframe="15m",
            candle_close_time="2026-08-26T00:15:00+00:00",
        )
        == key
    )
    assert repository.count_decision_chains() == 1


def test_order_schema_rejects_cross_mode_paper_link(repository: LedgerRepository) -> None:
    session_id = repository.create_paper_session(Decimal("100"))

    with pytest.raises(sqlite3.IntegrityError), repository.database.transaction() as connection:
        connection.execute(
            "INSERT INTO orders(id, mode, paper_account_id, client_order_id, side, "
            "quantity_text, status, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (
                "order-1",
                "live",
                session_id,
                "client-1",
                "BUY",
                "0.01",
                "PENDING",
                "2026-08-26T00:00:00+00:00",
            ),
        )


def test_genome_repository_transitions_and_active_resolution(database: Database) -> None:
    repo = GenomeRepository(database)
    genome = trend_pullback_v1()

    # Save baseline as candidate
    repo.save_genome(genome, origin="baseline", status="candidate")
    assert repo.get_genome("trend-pullback-v1") is not None

    # Baseline direct promotion to active by human is permitted
    repo.transition_genome_status("trend-pullback-v1", "active", promoted_by="human")
    active = repo.get_active_genome()
    assert active is not None
    assert active.genome_id == "trend-pullback-v1"

    # Hermes genome cannot jump from candidate to active directly
    hermes_genome = genome.model_copy(
        update={"genome_id": "hermes-proposal-1", "parent_id": "trend-pullback-v1"}
    )
    repo.save_genome(hermes_genome, origin="hermes", status="candidate")

    with pytest.raises(ValueError, match="invalid status transition"):
        repo.transition_genome_status("hermes-proposal-1", "active", promoted_by="gate")

    # Valid step: candidate -> shadow -> active
    repo.transition_genome_status("hermes-proposal-1", "shadow")
    repo.transition_genome_status("hermes-proposal-1", "active", promoted_by="gate")
    new_active = repo.get_active_genome()
    assert new_active is not None
    assert new_active.genome_id == "hermes-proposal-1"


def test_research_quota_repository(database: Database) -> None:
    quota_repo = QuotaRepository(database)
    today = "2026-08-26"

    # Consume backtests within limit
    assert quota_repo.consume_backtest(today, max_limit=2) is True
    assert quota_repo.consume_backtest(today, max_limit=2) is True
    # Exceeded limit
    assert quota_repo.consume_backtest(today, max_limit=2) is False

    # Web calls
    assert quota_repo.consume_web_call(today, max_limit=1) is True
    assert quota_repo.consume_web_call(today, max_limit=1) is False


def test_provider_routes_and_active_view(database: Database) -> None:
    prov_repo = ProviderRepository(database)
    prov_repo.upsert_provider(
        name="opencodex",
        kind="opencodex",
        base_url="http://localhost:10100",
        key_fingerprint="sha256-mock",
        status="active",
    )

    v1 = prov_repo.set_route("decision", "opencodex", "gemini-2.0-flash-lite", pinned=True)
    assert v1 == 1

    v2 = prov_repo.set_route(
        "decision", "opencodex", "google-antigravity/gemini-3.7-flash", pinned=True
    )
    assert v2 == 2

    routes = prov_repo.get_active_routes()
    assert routes["decision"].model == "google-antigravity/gemini-3.7-flash"
    assert routes["decision"].version == 2
