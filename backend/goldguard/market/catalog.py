from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, ConfigDict

from goldguard.domain.enums import ProductKind


class SymbolNotEligible(Exception):
    pass


class SymbolRule(BaseModel):
    model_config = ConfigDict(frozen=True)
    product: ProductKind
    symbol: str
    trading_status: str
    base_asset: str
    quote_asset: str
    tick_size: Decimal
    step_size: Decimal
    min_notional: Decimal
    min_quantity: Decimal
    max_quantity: Decimal
    max_leverage: int = 125
    observed_at: str


class CatalogSnapshot(BaseModel):
    model_config = ConfigDict(frozen=True)
    spot_rules: dict[str, SymbolRule]
    futures_rules: dict[str, SymbolRule]
    observed_at: str


def _parse_filter_value(
    filters: list[dict[str, Any]], filter_type: str, key: str, default: str
) -> Decimal:
    for f in filters:
        if f.get("filterType") == filter_type and key in f:
            try:
                return Decimal(str(f[key]))
            except Exception:
                pass
    return Decimal(default)


class SymbolCatalog:
    def __init__(self, spot_client: Any = None, futures_client: Any = None) -> None:
        self.spot_client = spot_client
        self.futures_client = futures_client
        self._snapshot: CatalogSnapshot | None = None

    async def refresh(self) -> CatalogSnapshot:
        now = datetime.now(UTC).isoformat()
        spot_rules: dict[str, SymbolRule] = {}
        futures_rules: dict[str, SymbolRule] = {}

        if self.spot_client is not None:
            try:
                info = await self.spot_client.exchange_info()
                symbols = info.get("symbols", [])
                for s in symbols:
                    sym = str(s["symbol"])
                    status = str(s.get("status", "TRADING"))
                    base = str(s.get("baseAsset", ""))
                    quote = str(s.get("quoteAsset", ""))
                    filters = s.get("filters", [])
                    tick = _parse_filter_value(filters, "PRICE_FILTER", "tickSize", "0.01")
                    step = _parse_filter_value(filters, "LOT_SIZE", "stepSize", "0.0001")
                    min_qty = _parse_filter_value(filters, "LOT_SIZE", "minQty", "0.0001")
                    max_qty = _parse_filter_value(filters, "LOT_SIZE", "maxQty", "1000000")
                    min_notional = _parse_filter_value(filters, "NOTIONAL", "minNotional", "5.00")
                    spot_rules[sym] = SymbolRule(
                        product=ProductKind.SPOT,
                        symbol=sym,
                        trading_status=status,
                        base_asset=base,
                        quote_asset=quote,
                        tick_size=tick,
                        step_size=step,
                        min_notional=min_notional,
                        min_quantity=min_qty,
                        max_quantity=max_qty,
                        max_leverage=1,
                        observed_at=now,
                    )
            except Exception:
                pass

        if self.futures_client is not None:
            try:
                info = await self.futures_client.exchange_info()
                symbols = info.get("symbols", [])
                for s in symbols:
                    sym = str(s["symbol"])
                    status = str(s.get("status", "TRADING"))
                    base = str(s.get("baseAsset", ""))
                    quote = str(s.get("quoteAsset", ""))
                    filters = s.get("filters", [])
                    tick = _parse_filter_value(filters, "PRICE_FILTER", "tickSize", "0.10")
                    step = _parse_filter_value(filters, "LOT_SIZE", "stepSize", "0.001")
                    min_qty = _parse_filter_value(filters, "LOT_SIZE", "minQty", "0.001")
                    max_qty = _parse_filter_value(filters, "LOT_SIZE", "maxQty", "1000000")
                    min_notional = _parse_filter_value(
                        filters, "MIN_NOTIONAL", "notional", "5.00"
                    )
                    futures_rules[sym] = SymbolRule(
                        product=ProductKind.FUTURES,
                        symbol=sym,
                        trading_status=status,
                        base_asset=base,
                        quote_asset=quote,
                        tick_size=tick,
                        step_size=step,
                        min_notional=min_notional,
                        min_quantity=min_qty,
                        max_quantity=max_qty,
                        max_leverage=125,
                        observed_at=now,
                    )
            except Exception:
                pass

        # Seed defaults if client was empty
        if not spot_rules:
            spot_rules["PAXGUSDT"] = SymbolRule(
                product=ProductKind.SPOT,
                symbol="PAXGUSDT",
                trading_status="TRADING",
                base_asset="PAXG",
                quote_asset="USDT",
                tick_size=Decimal("0.01"),
                step_size=Decimal("0.0001"),
                min_notional=Decimal("5.00"),
                min_quantity=Decimal("0.0001"),
                max_quantity=Decimal("1000"),
                max_leverage=1,
                observed_at=now,
            )
        if not futures_rules:
            for f_sym, tick, step in (
                ("BTCUSDT", Decimal("0.10"), Decimal("0.001")),
                ("ETHUSDT", Decimal("0.01"), Decimal("0.001")),
                ("SOLUSDT", Decimal("0.01"), Decimal("0.01")),
            ):
                futures_rules[f_sym] = SymbolRule(
                    product=ProductKind.FUTURES,
                    symbol=f_sym,
                    trading_status="TRADING",
                    base_asset=f_sym.replace("USDT", ""),
                    quote_asset="USDT",
                    tick_size=tick,
                    step_size=step,
                    min_notional=Decimal("5.00"),
                    min_quantity=step,
                    max_quantity=Decimal("100000"),
                    max_leverage=125,
                    observed_at=now,
                )

        snapshot = CatalogSnapshot(
            spot_rules=spot_rules,
            futures_rules=futures_rules,
            observed_at=now,
        )
        self._snapshot = snapshot
        return snapshot

    def get(self, product: ProductKind, symbol: str) -> SymbolRule | None:
        if self._snapshot is None:
            return None
        rules = (
            self._snapshot.spot_rules
            if product == ProductKind.SPOT
            else self._snapshot.futures_rules
        )
        return rules.get(symbol)

    def require(self, product: ProductKind, symbol: str) -> SymbolRule:
        rule = self.get(product, symbol)
        if rule is None:
            raise SymbolNotEligible(f"symbol {symbol} not found in {product.value} catalog")
        if rule.trading_status != "TRADING":
            raise SymbolNotEligible(
                f"symbol {symbol} is not actively trading (status: {rule.trading_status})"
            )
        return rule

