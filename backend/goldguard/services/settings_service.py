from dataclasses import dataclass
from decimal import Decimal, localcontext

from goldguard.domain.profile import ActiveProfile, AutonomousProfile
from goldguard.storage.profile_repository import ProfileRepository


class ProfileChangeBlocked(Exception):
    pass


@dataclass(frozen=True)
class RuntimeSafetySnapshot:
    has_open_positions: bool
    has_open_entry_orders: bool
    live_armed: bool
    account_equity_usdt: Decimal


@dataclass(frozen=True)
class SettingsPreview:
    profile: AutonomousProfile
    max_capital_per_trade_usdt: Decimal | None
    max_total_exposure_usdt: Decimal | None
    rolling_24h_loss_limit_usdt: Decimal | None
    blockers: tuple[str, ...]


def _same_execution_settings(current: AutonomousProfile, candidate: AutonomousProfile) -> bool:
    return current.model_copy(update={"notifications": candidate.notifications}) == candidate


def _is_scope_reduction(current: AutonomousProfile, candidate: AutonomousProfile) -> bool:
    if (
        current.execution_mode != candidate.execution_mode
        or current.strategy_mode != candidate.strategy_mode
        or current.autonomous_profile != candidate.autonomous_profile
        or current.risk != candidate.risk
    ):
        return False
    if candidate.spot_enabled and not current.spot_enabled:
        return False
    if candidate.futures_enabled and not current.futures_enabled:
        return False
    if not set(candidate.spot_pairs).issubset(current.spot_pairs):
        return False
    return set(candidate.futures_pairs).issubset(current.futures_pairs)


def _usdt_equivalent(rate: Decimal, equity: Decimal) -> Decimal:
    precision = max(
        28,
        equity.adjusted() + rate.adjusted() + 3,
        len(equity.as_tuple().digits) + len(rate.as_tuple().digits) + 2,
    )
    with localcontext() as context:
        context.prec = precision
        return (rate * equity).quantize(Decimal("0.01"))


class SettingsService:
    def __init__(self, repository: ProfileRepository) -> None:
        self._repository = repository

    def preview(
        self, candidate: AutonomousProfile, runtime: RuntimeSafetySnapshot
    ) -> SettingsPreview:
        blockers: list[str] = []
        active = self._repository.active()
        same_execution_settings = active is not None and _same_execution_settings(
            active.profile, candidate
        )
        scope_reduction = active is not None and _is_scope_reduction(active.profile, candidate)
        if runtime.has_open_positions and not (same_execution_settings or scope_reduction):
            blockers.append("Cannot change profile with an open position")
        if runtime.has_open_entry_orders and not same_execution_settings:
            blockers.append("Cannot change profile with open entry orders")

        equity = runtime.account_equity_usdt
        if not equity.is_finite() or equity < 0:
            blockers.append("account equity is unavailable")
            max_capital = None
            max_total = None
            rolling_loss = None
        else:
            max_capital = _usdt_equivalent(candidate.risk.max_capital_per_trade_rate, equity)
            max_total = _usdt_equivalent(candidate.risk.max_total_exposure_rate, equity)
            rolling_loss = _usdt_equivalent(candidate.risk.rolling_24h_loss_limit_rate, equity)

        return SettingsPreview(
            profile=candidate,
            max_capital_per_trade_usdt=max_capital,
            max_total_exposure_usdt=max_total,
            rolling_24h_loss_limit_usdt=rolling_loss,
            blockers=tuple(blockers),
        )

    def activate(
        self,
        candidate: AutonomousProfile,
        actor: str,
        correlation_id: str,
        runtime: RuntimeSafetySnapshot,
    ) -> ActiveProfile:
        preview = self.preview(candidate, runtime)
        if preview.blockers:
            raise ProfileChangeBlocked("; ".join(preview.blockers))
        return self._repository.activate(candidate, actor, correlation_id)
