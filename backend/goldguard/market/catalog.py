from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, ConfigDict

from goldguard.domain.enums import ProductKind


class SymbolNotEligible(Exception):
    pass


class CatalogRefreshError(RuntimeError):
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


def _required_filter_value(
    filters: list[dict[str, Any]], filter_types: tuple[str, ...], key: str
) -> Decimal:
    for item in filters:
        if item.get("filterType") not in filter_types or key not in item:
            continue
        try:
            value = Decimal(str(item[key]))
        except Exception as exc:
            raise ValueError(f"{filter_types[0]}.{key} is not decimal") from exc
        if value <= 0:
            raise ValueError(f"{filter_types[0]}.{key} must be positive")
        return value
    raise ValueError(f"required {filter_types[0]}.{key} is missing")


def _symbol_filter_values(
    filters: list[dict[str, Any]], *, futures: bool, trading: bool
) -> tuple[Decimal, Decimal, Decimal, Decimal, Decimal]:
    if not trading:
        placeholder = Decimal("1")
        return placeholder, placeholder, placeholder, placeholder, placeholder
    tick = _required_filter_value(filters, ("PRICE_FILTER",), "tickSize")
    step = _required_filter_value(filters, ("LOT_SIZE",), "stepSize")
    min_qty = _required_filter_value(filters, ("LOT_SIZE",), "minQty")
    max_qty = _required_filter_value(filters, ("LOT_SIZE",), "maxQty")
    if futures:
        min_notional = _required_filter_value(filters, ("MIN_NOTIONAL",), "notional")
    else:
        try:
            min_notional = _required_filter_value(filters, ("NOTIONAL",), "minNotional")
        except ValueError:
            min_notional = _required_filter_value(
                filters, ("MIN_NOTIONAL",), "minNotional"
            )
    return tick, step, min_qty, max_qty, min_notional


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
                    tick, step, min_qty, max_qty, min_notional = _symbol_filter_values(
                        filters,
                        futures=False,
                        trading=status == "TRADING",
                    )
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
            except Exception as exc:
                raise CatalogRefreshError(
                    f"spot catalog refresh failed; exchange filters are malformed: {exc}"
                ) from exc

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
                    tick, step, min_qty, max_qty, min_notional = _symbol_filter_values(
                        filters,
                        futures=True,
                        trading=status == "TRADING",
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
            except Exception as exc:
                raise CatalogRefreshError(
                    f"futures catalog refresh failed; exchange filters are malformed: {exc}"
                ) from exc

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
