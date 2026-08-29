from __future__ import annotations

from decimal import Decimal
from unittest.mock import AsyncMock

import pytest
from goldguard.domain.enums import ProductKind
from goldguard.market.catalog import SymbolCatalog, SymbolNotEligible


@pytest.fixture
def fake_binance() -> AsyncMock:
    client = AsyncMock()
    client.exchange_info = AsyncMock(
        return_value={
            "symbols": [
                {
                    "symbol": "PAXGUSDT",
                    "status": "TRADING",
                    "baseAsset": "PAXG",
                    "quoteAsset": "USDT",
                    "filters": [
                        {"filterType": "PRICE_FILTER", "tickSize": "0.01"},
                        {
                            "filterType": "LOT_SIZE",
                            "stepSize": "0.0001",
                            "minQty": "0.0001",
                            "maxQty": "1000",
                        },
                        {"filterType": "NOTIONAL", "minNotional": "5.00"},
                    ],
                },
                {
                    "symbol": "INACTIVESPOT",
                    "status": "BREAK",
                    "baseAsset": "INACTIVE",
                    "quoteAsset": "USDT",
                    "filters": [],
                },
            ]
        }
    )
    return client


@pytest.fixture
def fake_futures_binance() -> AsyncMock:
    client = AsyncMock()
    client.exchange_info = AsyncMock(
        return_value={
            "symbols": [
                {
                    "symbol": "BTCUSDT",
                    "status": "TRADING",
                    "baseAsset": "BTC",
                    "quoteAsset": "USDT",
                    "filters": [
                        {"filterType": "PRICE_FILTER", "tickSize": "0.10"},
                        {
                            "filterType": "LOT_SIZE",
                            "stepSize": "0.001",
                            "minQty": "0.001",
                            "maxQty": "1000",
                        },
                        {"filterType": "MIN_NOTIONAL", "notional": "5.00"},
                    ],
                }
            ]
        }
    )
    return client


@pytest.mark.asyncio
async def test_catalog_refresh_and_require_spot_and_futures(
    fake_binance: AsyncMock,
    fake_futures_binance: AsyncMock,
) -> None:
    catalog = SymbolCatalog(spot_client=fake_binance, futures_client=fake_futures_binance)
    await catalog.refresh()

    spot_rule = catalog.require(ProductKind.SPOT, "PAXGUSDT")
    assert spot_rule.symbol == "PAXGUSDT"
    assert spot_rule.tick_size == Decimal("0.01")
    assert spot_rule.step_size == Decimal("0.0001")

    futures_rule = catalog.require(ProductKind.FUTURES, "BTCUSDT")
    assert futures_rule.symbol == "BTCUSDT"
    assert futures_rule.tick_size == Decimal("0.10")


@pytest.mark.asyncio
async def test_catalog_rejects_wrong_product_and_nontrading_symbol(
    fake_binance: AsyncMock,
    fake_futures_binance: AsyncMock,
) -> None:
    catalog = SymbolCatalog(spot_client=fake_binance, futures_client=fake_futures_binance)
    await catalog.refresh()

    with pytest.raises(SymbolNotEligible, match="not found"):
        catalog.require(ProductKind.SPOT, "BTCUSD_PERP")

    with pytest.raises(SymbolNotEligible, match="not actively trading"):
        catalog.require(ProductKind.SPOT, "INACTIVESPOT")


@pytest.mark.asyncio
async def test_catalog_without_exchange_evidence_never_seeds_tradable_symbols() -> None:
    catalog = SymbolCatalog()
    snapshot = await catalog.refresh()

    assert snapshot.spot_rules == {}
    assert snapshot.futures_rules == {}
    with pytest.raises(SymbolNotEligible, match="not found"):
        catalog.require(ProductKind.SPOT, "PAXGUSDT")
