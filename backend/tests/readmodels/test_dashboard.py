from __future__ import annotations

from goldguard.readmodels.dashboard import DashboardOrderView, DashboardPositionView


def test_dashboard_read_models() -> None:
    order = DashboardOrderView(
        order_id="ord-1",
        client_order_id="c-1",
        symbol="BTCUSDT",
        product="futures",
        side="BUY",
        order_type="MARKET",
        quantity="0.01",
        price="60000.00",
        status="FILLED",
        created_at="2026-08-29T12:00:00+00:00",
    )
    assert order.symbol == "BTCUSDT"
    assert order.status == "FILLED"

    pos = DashboardPositionView(
        position_id="pos-1",
        symbol="ETHUSDT",
        product="futures",
        side="LONG",
        quantity="0.5",
        entry_price="2500.00",
        current_price="2550.00",
        gross_pnl_usdt="25.00",
        fees_usdt="0.50",
        funding_usdt="0.00",
        slippage_usdt="0.00",
        net_pnl_usdt="24.50",
        leverage=5,
    )
    assert pos.net_pnl_usdt == "24.50"

