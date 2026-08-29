from __future__ import annotations

from decimal import Decimal
from pathlib import Path

import pytest
from goldguard.broker.paper_futures import PaperFuturesBroker
from goldguard.broker.paper_portfolio import PaperPortfolioBroker
from goldguard.broker.paper_spot import PaperSpotBroker
from goldguard.domain.enums import ExecutionMode, ProductKind
from goldguard.domain.profile import default_autonomous_profile
from goldguard.execution.models import MarketScope
from goldguard.market.catalog import SymbolCatalog
from goldguard.risk.circuit_breaker import CircuitBreaker
from goldguard.services.emergency import EmergencyService
from goldguard.services.execution_coordinator import ExecutionCoordinator
from goldguard.services.market_supervisor import MarketSupervisor
from goldguard.services.runtime_supervisor import RuntimeSupervisor
from goldguard.storage.database import Database
from goldguard.storage.execution_repository import ExecutionRepository


def futures_scope(symbol: str) -> MarketScope:
    return MarketScope(mode=ExecutionMode.PAPER, product=ProductKind.FUTURES, symbol=symbol)


@pytest.mark.asyncio
async def test_scope_off_manages_existing_position_to_safe_exit(tmp_path: Path) -> None:
    db = Database(tmp_path / "supervisor_test.db")
    db.migrate()
    profile = default_autonomous_profile()

    catalog = SymbolCatalog()
    market = MarketSupervisor(catalog=catalog)
    spot = PaperSpotBroker(starting_cash=Decimal("10000.00"))
    futures = PaperFuturesBroker(starting_collateral=Decimal("10000.00"))
    broker = PaperPortfolioBroker(spot=spot, futures=futures)
    repo = ExecutionRepository(db)
    coordinator = ExecutionCoordinator(broker=broker, repository=repo, database=db)
    breaker = CircuitBreaker()
    emergency = EmergencyService(broker=broker, coordinator=coordinator)

    system = RuntimeSupervisor(
        profile=profile,
        market=market,
        broker=broker,
        coordinator=coordinator,
        breaker=breaker,
        emergency=emergency,
    )
    await system.start()

    btc = futures_scope("BTCUSDT")
    assert system.new_entries_allowed(btc) is True

    system.disable_scope(btc)
    assert system.new_entries_allowed(btc) is False
    assert system.protection_active("pos-1") is False

    await system.stop()
