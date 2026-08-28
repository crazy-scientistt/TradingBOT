from __future__ import annotations

from enum import StrEnum


class BotMode(StrEnum):
    PAPER = "paper"
    LIVE = "live"


class BotState(StrEnum):
    BOOTING = "BOOTING"
    DISARMED = "DISARMED"
    PAPER_READY = "PAPER_READY"
    LIVE_READ_ONLY = "LIVE_READ_ONLY"
    RUNNING_FLAT = "RUNNING_FLAT"
    RUNNING_OPEN = "RUNNING_OPEN"
    COOLDOWN = "COOLDOWN"
    RISK_HALTED = "RISK_HALTED"
    DATA_HALTED = "DATA_HALTED"
    RECOVERY_REQUIRED = "RECOVERY_REQUIRED"
    EMERGENCY_STOPPED = "EMERGENCY_STOPPED"
    # Autonomy & research lifecycle states
    RESEARCH_ACTIVE = "RESEARCH_ACTIVE"
    AUTONOMY_SUSPENDED = "AUTONOMY_SUSPENDED"
    QUARANTINE = "QUARANTINE"


class CandidateAction(StrEnum):
    ENTRY_CANDIDATE = "ENTRY_CANDIDATE"
    EXIT_CANDIDATE = "EXIT_CANDIDATE"
    NO_ACTION = "NO_ACTION"


class AiDecision(StrEnum):
    APPROVE_ENTRY = "APPROVE_ENTRY"
    REJECT_ENTRY = "REJECT_ENTRY"
    EXIT = "EXIT"
    HOLD = "HOLD"


class OrderSide(StrEnum):
    BUY = "BUY"
    SELL = "SELL"


class ExitReason(StrEnum):
    STOP_LOSS = "STOP_LOSS"
    TAKE_PROFIT = "TAKE_PROFIT"
    REGIME_INVALIDATION = "REGIME_INVALIDATION"
    AI_RISK_REDUCTION = "AI_RISK_REDUCTION"
    EMERGENCY = "EMERGENCY"


class ChecklistAction(StrEnum):
    PASS = "PASS"
    HOLD = "HOLD"


class ExecutionMode(StrEnum):
    PAPER = "paper"
    LIVE = "live"


class StrategyMode(StrEnum):
    LEGACY = "legacy"
    AUTONOMOUS = "autonomous"


class AutonomousProfileKind(StrEnum):
    MICRO_TRADE = "micro_trade"
    STANDARD = "standard"


class ProductKind(StrEnum):
    SPOT = "spot"
    FUTURES = "futures"
