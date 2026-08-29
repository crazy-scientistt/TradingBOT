from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

from goldguard.broker.paper import PaperBroker
from goldguard.domain.models import Quote, TradePlan


def test_legacy_paper_broker_preserved() -> None:
    broker = PaperBroker(
        starting_cash=Decimal("10000.00"),
        fee_rate=Decimal("0.001"),
        slippage_rate=Decimal("0.0002"),
    )
    assert broker.cash == Decimal("10000.00")
    assert broker.position is None

    quote = Quote(
        symbol="PAXGUSDT",
        bid=Decimal("2000.00"),
        ask=Decimal("2000.50"),
        last=Decimal("2000.25"),
        observed_at=datetime.now(UTC),
    )
    plan = TradePlan(
        entry=Decimal("2000.50"),
        stop=Decimal("1950.00"),
        target=Decimal("2100.00"),
        quantity=Decimal("1.0"),
        risk_amount=Decimal("50.50"),
        expected_fees=Decimal("4.00"),
    )
    fill = broker.open_long(plan, quote, client_order_id="leg-1")
    assert fill.quantity == Decimal("1.0")
    assert broker.position is not None

