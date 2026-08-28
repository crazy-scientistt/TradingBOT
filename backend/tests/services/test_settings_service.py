from decimal import Decimal

import pytest
from goldguard.domain.profile import AutonomousProfile, NotificationPreferences
from goldguard.services.settings_service import (
    ProfileChangeBlocked,
    RuntimeSafetySnapshot,
    SettingsService,
)
from goldguard.storage.database import Database
from goldguard.storage.profile_repository import ProfileRepository


@pytest.fixture
def repository(tmp_path):
    db = Database(tmp_path / "test.db")
    db.migrate()
    return ProfileRepository(db)


@pytest.fixture
def service(repository):
    return SettingsService(repository)


def candidate_profile():
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


def test_rejected_balance_change_does_not_activate_profile(service, repository) -> None:
    before = repository.active()
    unsafe = RuntimeSafetySnapshot(
        has_open_positions=True,
        has_open_entry_orders=False,
        live_armed=False,
        account_equity_usdt=Decimal("1000"),
    )
    with pytest.raises(ProfileChangeBlocked, match="open position"):
        service.activate(candidate_profile(), "admin", "corr-1", unsafe)
    assert repository.active() == before


def test_preview_returns_live_usdt_equivalents(service) -> None:
    preview = service.preview(
        candidate_profile(),
        RuntimeSafetySnapshot(False, False, False, Decimal("10000")),
    )
    assert preview.max_capital_per_trade_usdt == Decimal("50.00")


def test_preview_marks_non_finite_equity_unavailable(service) -> None:
    preview = service.preview(
        candidate_profile(),
        RuntimeSafetySnapshot(False, False, False, Decimal("NaN")),
    )

    assert preview.max_capital_per_trade_usdt is None
    assert preview.max_total_exposure_usdt is None
    assert preview.rolling_24h_loss_limit_usdt is None
    assert "account equity is unavailable" in preview.blockers


def test_preview_supports_large_finite_equity(service) -> None:
    preview = service.preview(
        candidate_profile(),
        RuntimeSafetySnapshot(False, False, False, Decimal("1E+30")),
    )

    assert preview.max_capital_per_trade_usdt == Decimal("5E+27")


def test_notification_change_is_allowed_with_an_open_position(service, repository) -> None:
    active = candidate_profile()
    repository.activate(active, "admin", "corr-1")
    notification_only = active.model_copy(
        update={"notifications": NotificationPreferences(telegram_enabled=True)}
    )
    runtime = RuntimeSafetySnapshot(True, False, False, Decimal("1000"))

    preview = service.preview(notification_only, runtime)

    assert preview.blockers == ()


def test_scope_reduction_is_allowed_with_an_open_position(service, repository) -> None:
    active = candidate_profile()
    repository.activate(active, "admin", "corr-1")
    scope_reduction = active.model_copy(update={"futures_enabled": False, "futures_pairs": ()})
    runtime = RuntimeSafetySnapshot(True, False, True, Decimal("1000"))

    preview = service.preview(scope_reduction, runtime)

    assert preview.blockers == ()
