from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

from goldguard.broker.base import ClosedPaperTrade, PaperFill
from goldguard.domain.enums import ExitReason, OrderSide
from goldguard.memory.recorder import LearningRecorder
from goldguard.storage.database import Database
from goldguard.storage.repositories import ReflectionRepository


def _trade() -> ClosedPaperTrade:
    when = datetime(2026, 8, 30, tzinfo=UTC)
    entry = PaperFill(
        client_order_id="entry-1",
        side=OrderSide.BUY,
        quantity=Decimal("0.01"),
        price=Decimal("2500"),
        fee=Decimal("0.025"),
        filled_at=when,
    )
    exit_fill = PaperFill(
        client_order_id="exit-1",
        side=OrderSide.SELL,
        quantity=Decimal("0.01"),
        price=Decimal("2520"),
        fee=Decimal("0.025"),
        filled_at=when,
    )
    return ClosedPaperTrade(
        entry_fill=entry,
        exit_fill=exit_fill,
        exit_reason=ExitReason.TAKE_PROFIT,
        realized_pnl=Decimal("0.15"),
    )


def test_closed_trade_writes_exactly_one_reflection(tmp_path: Path) -> None:
    db = Database(tmp_path / "learn.db")
    db.migrate()
    repo = ReflectionRepository(db)
    recorder = LearningRecorder(repo)
    trade = _trade()
    first = recorder.record_closed_trade(trade, trade_id="trade-1", symbol="PAXGUSDT")
    second = recorder.record_closed_trade(trade, trade_id="trade-1", symbol="PAXGUSDT")
    rows = repo.list_reflections(namespace="forward")
    assert first is not None
    assert second is None
    assert len(rows) == 1
    assert rows[0]["trade_id"] == "trade-1"
