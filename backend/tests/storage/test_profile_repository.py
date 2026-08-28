import json
from decimal import Decimal

from goldguard.domain.profile import AutonomousProfile, NotificationPreferences
from goldguard.storage.database import Database
from goldguard.storage.profile_repository import ProfileRepository


def test_profile_repository_activate_and_read(tmp_path) -> None:
    db = Database(tmp_path / "test.db")
    db.migrate()
    repo = ProfileRepository(db)

    assert repo.active() is None

    profile = AutonomousProfile.model_validate(
        {
            "execution_mode": "paper",
            "strategy_mode": "autonomous",
            "autonomous_profile": "micro_trade",
            "spot_enabled": True,
            "futures_enabled": True,
            "spot_pairs": ["PAXGUSDT"],
            "futures_pairs": ["BTCUSDT", "ETHUSDT"],
            "risk": {
                "max_capital_per_trade_rate": "0.005",
                "max_futures_leverage": 5,
                "max_total_exposure_rate": "0.20",
                "rolling_24h_loss_limit_rate": "0.03",
            },
        }
    )

    activated = repo.activate(profile, "admin", "corr-1")
    read_back = repo.active()

    assert read_back is not None
    assert read_back.hash == activated.hash
    assert read_back.profile == profile


def candidate_profile() -> AutonomousProfile:
    return AutonomousProfile.model_validate(
        {
            "execution_mode": "paper",
            "strategy_mode": "autonomous",
            "autonomous_profile": "micro_trade",
            "spot_enabled": True,
            "futures_enabled": True,
            "spot_pairs": ["PAXGUSDT"],
            "futures_pairs": ["BTCUSDT", "ETHUSDT"],
            "risk": {
                "max_capital_per_trade_rate": "0.005",
                "max_futures_leverage": 5,
                "max_total_exposure_rate": "0.20",
                "rolling_24h_loss_limit_rate": "0.03",
            },
        }
    )


def armed_repository(tmp_path) -> tuple[Database, ProfileRepository, AutonomousProfile]:
    database = Database(tmp_path / "armed.db")
    database.migrate()
    repository = ProfileRepository(database)
    profile = candidate_profile()
    active = repository.activate(profile, "admin", "corr-1")
    with database.transaction() as connection:
        connection.execute(
            "UPDATE live_arming_state "
            "SET status = 'armed_ready', profile_hash = ?, "
            "expected_equity_usdt = '10000.00', armed_at = ?, armed_by = 'admin' "
            "WHERE id = 1",
            (active.hash, "2026-08-29T00:00:00+00:00"),
        )
    return database, repository, profile


def arming_status(database: Database) -> str:
    with database.connect() as connection:
        row = connection.execute("SELECT status FROM live_arming_state WHERE id = 1").fetchone()
    assert row is not None
    return str(row["status"])


def test_reactivation_returns_the_persisted_version_metadata(tmp_path) -> None:
    database = Database(tmp_path / "reactivation.db")
    database.migrate()
    repository = ProfileRepository(database)
    profile = candidate_profile()
    first = repository.activate(profile, "first-admin", "corr-1")

    reactivated = repository.activate(profile, "second-admin", "corr-2")

    assert reactivated == repository.active()
    assert reactivated.created_at == first.created_at
    assert reactivated.created_by == "first-admin"
    with database.connect() as connection:
        version_count = connection.execute("SELECT COUNT(*) FROM profile_versions").fetchone()[0]
    assert version_count == 1


def test_semantically_equal_decimal_scales_share_one_profile_version(tmp_path) -> None:
    database = Database(tmp_path / "canonical.db")
    database.migrate()
    repository = ProfileRepository(database)
    profile = candidate_profile()
    equivalent_risk = profile.risk.model_copy(
        update={"max_capital_per_trade_rate": Decimal("0.0050")}
    )
    equivalent = profile.model_copy(update={"risk": equivalent_risk})

    first = repository.activate(profile, "admin", "corr-1")
    second = repository.activate(equivalent, "admin", "corr-2")

    assert second.hash == first.hash
    with database.connect() as connection:
        version_count = connection.execute("SELECT COUNT(*) FROM profile_versions").fetchone()[0]
    assert version_count == 1


def test_semantically_equal_pair_order_shares_one_profile_version(tmp_path) -> None:
    database, repository, profile = armed_repository(tmp_path)
    first = repository.active()
    assert first is not None
    reordered = profile.model_copy(update={"futures_pairs": ("ETHUSDT", "BTCUSDT")})

    second = repository.activate(reordered, "admin", "corr-2")

    assert second.hash == first.hash
    assert arming_status(database) == "armed_ready"


def test_canonical_profile_preserves_high_precision_decimal(tmp_path) -> None:
    database = Database(tmp_path / "precision.db")
    database.migrate()
    repository = ProfileRepository(database)
    profile = candidate_profile()
    precise_rate = Decimal("0.123456789012345678901234567890")
    precise_risk = profile.risk.model_copy(update={"max_capital_per_trade_rate": precise_rate})
    precise_profile = profile.model_copy(update={"risk": precise_risk})

    active = repository.activate(precise_profile, "admin", "corr-1")

    assert active.profile.risk.max_capital_per_trade_rate == precise_rate


def test_notification_only_change_keeps_live_arming_ready(tmp_path) -> None:
    database, repository, profile = armed_repository(tmp_path)
    notification_only = profile.model_copy(
        update={"notifications": NotificationPreferences(telegram_enabled=True)}
    )

    active = repository.activate(notification_only, "admin", "corr-2")

    assert arming_status(database) == "armed_ready"
    with database.connect() as connection:
        armed_profile_hash = connection.execute(
            "SELECT profile_hash FROM live_arming_state WHERE id = 1"
        ).fetchone()[0]
    assert armed_profile_hash == active.hash


def test_execution_change_requires_live_reconciliation(tmp_path) -> None:
    database, repository, profile = armed_repository(tmp_path)
    changed_risk = profile.risk.model_copy(update={"max_capital_per_trade_rate": Decimal("0.01")})
    execution_change = profile.model_copy(update={"risk": changed_risk})

    repository.activate(execution_change, "admin", "corr-2")

    assert arming_status(database) == "armed_pending_reconciliation"


def test_activation_audit_records_prior_new_state_and_outcome(tmp_path) -> None:
    database = Database(tmp_path / "audit.db")
    database.migrate()
    repository = ProfileRepository(database)
    profile = candidate_profile()
    first = repository.activate(profile, "admin", "corr-1")
    changed_risk = profile.risk.model_copy(update={"max_capital_per_trade_rate": Decimal("0.01")})
    changed = profile.model_copy(update={"risk": changed_risk})

    second = repository.activate(changed, "admin", "corr-2")

    with database.connect() as connection:
        row = connection.execute(
            "SELECT metadata FROM security_events WHERE correlation_id = 'corr-2'"
        ).fetchone()
    assert row is not None
    metadata = json.loads(row["metadata"])
    assert metadata["previous_profile_hash"] == first.hash
    assert metadata["new_profile_hash"] == second.hash
    assert metadata["previous_profile"]["risk"]["max_capital_per_trade_rate"] == "0.005"
    assert metadata["new_profile"]["risk"]["max_capital_per_trade_rate"] == "0.01"
    assert metadata["outcome"] == "success"
