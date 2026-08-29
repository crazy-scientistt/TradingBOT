from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any, cast

from goldguard.domain.models import Quote
from goldguard.execution.models import MarketScope
from goldguard.market.catalog import SymbolCatalog
from goldguard.services.ingestion import MarketSnapshot


class MarketSupervisor:
    def __init__(self, catalog: SymbolCatalog, clock: Any = None) -> None:
        self.catalog = catalog
        self.clock = clock
        self._scopes: tuple[MarketScope, ...] = ()
        self._quotes: dict[MarketScope, Quote] = {}
        self._snapshots: dict[MarketScope, MarketSnapshot] = {}
        self._running = False

    def _now(self) -> datetime:
        if self.clock is not None:
            return cast(datetime, self.clock.now())
        return datetime.now(UTC)

    async def start(self, scopes: tuple[MarketScope, ...] | list[MarketScope]) -> None:
        self._scopes = tuple(scopes)
        self._running = True
        if self.catalog._snapshot is None:
            await self.catalog.refresh()

    def record_quote(self, scope: MarketScope, quote: Quote) -> None:
        self._quotes[scope] = quote

    def fresh(self, scope: MarketScope, max_age: timedelta) -> bool:
        quote = self._quotes.get(scope)
        if quote is None:
            return False
        now = self._now()
        observed = quote.observed_at
        if observed.tzinfo is None:
            observed = observed.replace(tzinfo=UTC)
        if now.tzinfo is None:
            now = now.replace(tzinfo=UTC)
        return now - observed <= max_age

    def snapshot(self, scope: MarketScope) -> MarketSnapshot | None:
        quote = self._quotes.get(scope)
        is_fresh = self.fresh(scope, timedelta(seconds=30))
        return MarketSnapshot(
            availability="available" if is_fresh and quote is not None else "unavailable",
            source="market_supervisor",
            observed_at=quote.observed_at if quote else None,
            stale=not is_fresh,
            detail=None if is_fresh else "quote stream stale or unavailable",
            verified=is_fresh,
            candles_15m=(),
            candles_1h=(),
            latest_quote=quote,
            filters=None,
        )

    async def stop(self) -> None:
        self._running = False

