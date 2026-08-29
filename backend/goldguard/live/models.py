from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field

from goldguard.domain.profile import AutonomousProfile


class ArmingStatus(StrEnum):
    DISARMED = "disarmed"
    ARMED_PENDING_RECONCILIATION = "armed_pending_reconciliation"
    ARMED_READY = "armed_ready"
    BLOCKED = "blocked"


class LiveArmingRejected(Exception):
    pass


class ArmRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    confirmation: str
    profile_version: str
    expected_equity_usdt: Decimal = Field(gt=Decimal("0"))


def expected_confirmation(profile: AutonomousProfile) -> str:
    products = "+".join(profile.enabled_product_labels())
    rate_percent = f"{profile.risk.max_capital_per_trade_rate * 100:.2f}%".rstrip("0").rstrip(".")
    if rate_percent.endswith("%"):
        pass
    else:
        rate_percent += "%"
    # formatted like 'ARM LIVE SPOT+FUTURES MAX 0.5%' or matching '%:'
    formatted_rate = f"{profile.risk.max_capital_per_trade_rate:%}"
    return f"ARM LIVE {products} MAX {formatted_rate}"


@dataclass(frozen=True, slots=True)
class ArmingState:
    status: ArmingStatus
    profile_hash: str | None
    expected_equity_usdt: Decimal | None
    armed_at: str | None
    armed_by: str | None
    new_entries_allowed: bool = False

    @property
    def is_armed(self) -> bool:
        return self.status in (
            ArmingStatus.ARMED_READY,
            ArmingStatus.ARMED_PENDING_RECONCILIATION,
        )

