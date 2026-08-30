from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

from goldguard.broker.base import ClosedPaperTrade, PaperFill
from goldguard.domain.enums import ExitReason, OrderSide
from goldguard.memory.recorder import LearningRecorder
from goldguard.storage.database import Database
from goldguard.storage.repositories import GenomeRepository, QuotaRepository, ReflectionRepository
from goldguard.strategy.genome import genome_hash, trend_pullback_v1


def test_genome_reflections_and_quota_survive_reopen(tmp_path: Path) -> None:
    path = tmp_path / "ledger.db"
    first = Database(path)
    first.migrate()
    genomes = GenomeRepository(first)
    baseline = trend_pullback_v1()
    genomes.save_genome(baseline, origin="baseline", status="active")
    quota = QuotaRepository(first)
    assert quota.consume_backtest("2026-08-30", max_limit=8)
    trade = ClosedPaperTrade(
        entry_fill=PaperFill(
            client_order_id="e1",
            side=OrderSide.BUY,
            quantity=Decimal("0.01"),
            price=Decimal("2500"),
            fee=Decimal("0.02"),
            filled_at=datetime(2026, 8, 30, tzinfo=UTC),
        ),
        exit_fill=PaperFill(
            client_order_id="x1",
            side=OrderSide.SELL,
            quantity=Decimal("0.01"),
            price=Decimal("2510"),
            fee=Decimal("0.02"),
            filled_at=datetime(2026, 8, 30, tzinfo=UTC),
        ),
        exit_reason=ExitReason.TAKE_PROFIT,
        realized_pnl=Decimal("0.06"),
    )
    LearningRecorder(ReflectionRepository(first)).record_closed_trade(
        trade, trade_id="trade-restart-1", symbol="PAXGUSDT"
    )

    restarted = Database(path)
    restarted.migrate()
    again = GenomeRepository(restarted).get_active_genome()
    assert again is not None
    assert genome_hash(again) == genome_hash(baseline)
    rows = ReflectionRepository(restarted).list_reflections()
    assert len(rows) == 1
    assert rows[0]["trade_id"] == "trade-restart-1"
    LearningRecorder(ReflectionRepository(restarted)).record_closed_trade(
        trade, trade_id="trade-restart-1", symbol="PAXGUSDT"
    )
    assert len(ReflectionRepository(restarted).list_reflections()) == 1
    assert QuotaRepository(restarted).get_usage("2026-08-30")[0] == 1
