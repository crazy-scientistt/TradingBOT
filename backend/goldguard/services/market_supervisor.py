from __future__ import annotations

import asyncio
from collections.abc import Mapping
from contextlib import suppress
from datetime import UTC, datetime, timedelta
from typing import Any, Protocol, cast

from goldguard.domain.enums import ProductKind
from goldguard.domain.models import Quote
from goldguard.execution.models import MarketScope
from goldguard.market.catalog import SymbolCatalog
from goldguard.services.ingestion import MarketSnapshot


class MarketSupervisor:

    def __init__(
        self,
        catalog: SymbolCatalog,
        clock: Any = None,
        quote_sources: Mapping[ProductKind, QuoteSource] | None = None,
        poll_seconds: float = 1.0,
    ) -> None:
        self.catalog = catalog
        self.clock = clock
        self._quote_sources = dict(quote_sources or {})
        self._poll_seconds = poll_seconds
        self._scopes: tuple[MarketScope, ...] = ()
        self._quotes: dict[MarketScope, Quote] = {}
        self._snapshots: dict[MarketScope, MarketSnapshot] = {}
        self._errors: dict[MarketScope, str] = {}
        self._task: asyncio.Task[None] | None = None
        self._running = False

    @property
    def running(self) -> bool:
        return self._running

    def _now(self) -> datetime:
        if self.clock is not None:
            return cast(datetime, self.clock.now())
        return datetime.now(UTC)

    async def start(self, scopes: tuple[MarketScope, ...] | list[MarketScope]) -> None:
        if self._running:
            return
        self._scopes = tuple(scopes)
        if self.catalog._snapshot is None:
            await self.catalog.refresh()
        for scope in self._scopes:
            self.catalog.require(scope.product, scope.symbol)
        self._running = True
        if self._quote_sources:
            await self._poll_once()
            self._task = asyncio.create_task(self._poll_loop(), name="market-supervisor")

    def record_quote(self, scope: MarketScope, quote: Quote) -> None:
        if scope not in self._scopes:
            raise ValueError(f"scope {scope.product.value}:{scope.symbol} is not supervised")
        self._quotes[scope] = quote
        self._errors.pop(scope, None)

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
            detail=(
                None
                if is_fresh
                else self._errors.get(scope, "quote stream stale or unavailable")
            ),
            verified=is_fresh,
            candles_15m=(),
            candles_1h=(),
            latest_quote=quote,
            filters=None,
        )

    async def stop(self) -> None:
        self._running = False
        if self._task is not None:
            self._task.cancel()
            with suppress(asyncio.CancelledError):
                await self._task
            self._task = None

    async def _poll_once(self) -> None:
        for scope in self._scopes:
            source = self._quote_sources.get(scope.product)
            if source is None:
                self._errors[scope] = f"no {scope.product.value} quote source configured"
                continue
            try:
                quote = await source.quote(scope.symbol, observed_at=self._now())
            except Exception as exc:
                self._errors[scope] = f"quote source failed: {exc}"
                continue
            self.record_quote(scope, quote)

    async def _poll_loop(self) -> None:
        while self._running:
            await asyncio.sleep(self._poll_seconds)
            await self._poll_once()


class QuoteSource(Protocol):
    async def quote(self, symbol: str, *, observed_at: datetime | None = None) -> Quote: ...
