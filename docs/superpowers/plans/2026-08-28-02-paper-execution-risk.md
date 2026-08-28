# Paper Execution and Portfolio Risk Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the single-position PAXG Paper runtime with truthful multi-pair Spot and USD-M Futures Paper execution, account-wide deterministic risk, stale-data safety, circuit breakers, and optional Micro-Trade operation while preserving Legacy behavior.

**Architecture:** Introduce product-neutral order/position contracts and separate Spot/Futures Paper brokers behind one async execution protocol. A portfolio risk service owns exposure, costs, leverage, correlation, and breakers; per-pair locks and durable intents prevent duplicate concurrent entries.

**Tech Stack:** Python 3.12, Pydantic 2, Decimal, asyncio, SQLite/WAL, Binance public REST/WebSocket, pytest, Hypothesis, Ruff, mypy strict.

**Spec:** `docs/superpowers/specs/2026-08-28-autonomous-hermes-trading-platform-design.md`

## Global Constraints

- No Live order; all broker behavior in this plan is simulated.
- Preserve `PaperBroker` as the Legacy adapter until parity tests pass.
- Spot supports cash-only `PAXGUSDT`; Futures supports validated USD-M pairs, isolated margin, One-way Mode.
- User values are ceilings; actual allocation/leverage can only be lower.
- Micro-Trade frequency never overrides net-edge, freshness, exposure, or breaker gates.
- Existing position protection and exit monitoring continue when entries are paused or a scope is disabled.

---

### Task 1: Product-neutral execution contracts and ledger migration

**Files:**
- Create: `backend/goldguard/execution/__init__.py`
- Create: `backend/goldguard/execution/models.py`
- Create: `backend/goldguard/execution/protocols.py`
- Create: `backend/goldguard/storage/migrations/004_execution_ledger.sql`
- Modify: `backend/goldguard/domain/enums.py`
- Test: `backend/tests/execution/test_models.py`
- Test: `backend/tests/storage/test_execution_migration.py`

**Interfaces:**
- `MarketScope`, `OrderIntent`, `OrderRecord`, `FillRecord`, `PositionRecord`, `AccountSnapshot`, `ProtectionPlan`, `ExecutionResult`.
- `ExecutionBroker.submit(intent)`, `cancel(client_order_id)`, `close(position_id, reason)`, `snapshot()` are async.
- Ledger adds product/symbol/position side/order type/reduce-only/exchange IDs/margin/leverage/funding/slippage/ownership and protection relationships without deleting legacy rows.

- [ ] **Step 1: Write failing model and migration tests**

```python
def test_futures_intent_requires_isolated_margin_and_leverage() -> None:
    intent = OrderIntent.model_validate({
        "intent_id": "intent-1", "client_order_id": "gg-1",
        "mode": "paper", "product": "futures", "symbol": "BTCUSDT",
        "side": "BUY", "position_side": "LONG", "order_type": "MARKET",
        "quantity": "0.001", "margin_mode": "isolated", "leverage": 3,
        "reduce_only": False,
    })
    assert intent.margin_mode == MarginMode.ISOLATED


def test_execution_migration_preserves_existing_orders(database) -> None:
    seed_legacy_order(database)
    database.migrate()
    assert load_order(database, "legacy-order").product == "spot"
```

- [ ] **Step 2: Run failing tests**

```powershell
$testBase = Join-Path $env:TEMP "pytest-goldguard-execution-models-red"
uv run pytest backend/tests/execution/test_models.py backend/tests/storage/test_execution_migration.py -q -p no:cacheprovider --basetemp $testBase
```

- [ ] **Step 3: Implement immutable contracts and additive schema**

```python
class ExecutionBroker(Protocol):
    async def submit(self, intent: OrderIntent) -> ExecutionResult: ...
    async def cancel(self, client_order_id: str) -> OrderRecord: ...
    async def close(self, position_id: str, reason: ExitReason) -> ExecutionResult: ...
    async def snapshot(self) -> AccountSnapshot: ...
```

`004_execution_ledger.sql` adds normalized execution-intent, order, fill, position, protection, funding, account-snapshot, and ownership tables. Unique keys cover `(mode, account_scope, client_order_id)` and exchange IDs.

- [ ] **Step 4: Run model/storage suites**

```powershell
$testBase = Join-Path $env:TEMP "pytest-goldguard-execution-models-green"
uv run pytest backend/tests/execution/test_models.py backend/tests/storage/test_execution_migration.py backend/tests/storage -q -p no:cacheprovider --basetemp $testBase
uv run ruff check backend/goldguard/execution backend/goldguard/storage backend/tests/execution
uv run mypy backend/goldguard/execution backend/goldguard/storage
```

- [ ] **Step 5: Commit**

```powershell
git add backend/goldguard/execution backend/goldguard/domain/enums.py backend/goldguard/storage/migrations/004_execution_ledger.sql backend/tests/execution backend/tests/storage/test_execution_migration.py
git commit -m "feat: add product-neutral execution ledger"
```

### Task 2: Validated symbol catalog and multi-pair market supervisor

**Files:**
- Create: `backend/goldguard/market/catalog.py`
- Create: `backend/goldguard/services/market_supervisor.py`
- Modify: `backend/goldguard/market/binance.py`
- Modify: `backend/goldguard/market/live_stream.py`
- Modify: `backend/goldguard/services/ingestion.py`
- Test: `backend/tests/market/test_catalog.py`
- Test: `backend/tests/services/test_market_supervisor.py`

**Interfaces:**
- `SymbolCatalog.refresh() -> CatalogSnapshot`
- `SymbolRule` includes product, symbol, trading status, base/quote, tick size, step size, minimum notional, leverage bounds, and observed time.
- `MarketSupervisor.start(scopes: tuple[MarketScope, ...])`, `snapshot(scope)`, `fresh(scope, max_age)`, `stop()`.

- [ ] **Step 1: Write failing scope/freshness tests**

```python
async def test_catalog_rejects_wrong_product_and_nontrading_symbol(fake_binance) -> None:
    catalog = await SymbolCatalog(fake_binance).refresh()
    with pytest.raises(SymbolNotEligible):
        catalog.require(ProductKind.SPOT, "BTCUSD_PERP")


async def test_supervisor_marks_silent_stream_stale(supervisor, clock) -> None:
    await supervisor.start((spot_scope("PAXGUSDT"), futures_scope("BTCUSDT")))
    clock.advance(timedelta(seconds=31))
    assert supervisor.fresh(futures_scope("BTCUSDT"), timedelta(seconds=30)) is False
```

- [ ] **Step 2: Verify tests fail**

```powershell
$testBase = Join-Path $env:TEMP "pytest-goldguard-market-supervisor-red"
uv run pytest backend/tests/market/test_catalog.py backend/tests/services/test_market_supervisor.py -q -p no:cacheprovider --basetemp $testBase
```

- [ ] **Step 3: Implement product-aware clients and watchdog-owned freshness**

```python
@dataclass(frozen=True)
class MarketScope:
    product: ProductKind
    symbol: str


class MarketSupervisor:
    def fresh(self, scope: MarketScope, max_age: timedelta) -> bool:
        quote = self._snapshots[scope].quote
        return quote is not None and self._clock.now() - quote.observed_at <= max_age
```

REST and WebSocket updates publish into one per-scope queue. A timed watchdog updates stale health even when no quote arrives. Chart history remains separate from execution freshness.

- [ ] **Step 4: Run market/ingestion suites**

```powershell
$testBase = Join-Path $env:TEMP "pytest-goldguard-market-supervisor-green"
uv run pytest backend/tests/market backend/tests/services/test_market_ingestion.py backend/tests/services/test_market_supervisor.py -q -p no:cacheprovider --basetemp $testBase
uv run ruff check backend/goldguard/market backend/goldguard/services/market_supervisor.py backend/tests/market
uv run mypy backend/goldguard/market backend/goldguard/services/market_supervisor.py
```

- [ ] **Step 5: Commit**

```powershell
git add backend/goldguard/market backend/goldguard/services/market_supervisor.py backend/goldguard/services/ingestion.py backend/tests/market backend/tests/services/test_market_supervisor.py
git commit -m "feat: supervise validated multi-pair markets"
```

### Task 3: Multi-position Paper Spot and Futures brokers

**Files:**
- Create: `backend/goldguard/broker/paper_portfolio.py`
- Create: `backend/goldguard/broker/paper_spot.py`
- Create: `backend/goldguard/broker/paper_futures.py`
- Modify: `backend/goldguard/broker/__init__.py`
- Test: `backend/tests/broker/test_paper_spot.py`
- Test: `backend/tests/broker/test_paper_futures.py`
- Test: `backend/tests/broker/test_paper_portfolio.py`
- Test: `backend/tests/e2e/test_legacy_parity.py`

**Interfaces:**
- `PaperPortfolioBroker` delegates by product and owns USDT-equivalent equity/exposure snapshots.
- Spot fills reserve/release quote cash and never create debt.
- Futures fills reserve isolated margin, apply selected leverage, mark unrealized P&L, funding, fees, maintenance margin, and liquidation estimate.

- [ ] **Step 1: Write failing financial invariants**

```python
async def test_spot_cannot_spend_more_than_available_cash(spot_broker) -> None:
    with pytest.raises(InsufficientBalance):
        await spot_broker.submit(spot_buy_intent(notional="101", cash="100"))


async def test_futures_position_is_isolated_and_cost_adjusted(futures_broker) -> None:
    result = await futures_broker.submit(futures_long_intent(margin="10", leverage=5))
    position = result.position
    assert position.margin_mode == MarginMode.ISOLATED
    assert position.initial_margin == Decimal("10")
    assert position.net_pnl == position.gross_pnl - position.fees - position.funding


def test_legacy_strategy_replays_identically(legacy_fixture) -> None:
    before = legacy_fixture.run_original_paper_broker()
    after = legacy_fixture.run_legacy_adapter()
    assert after.fills == before.fills
    assert after.ending_equity == before.ending_equity
```

- [ ] **Step 2: Run failing broker tests**

```powershell
$testBase = Join-Path $env:TEMP "pytest-goldguard-paper-brokers-red"
uv run pytest backend/tests/broker/test_paper_spot.py backend/tests/broker/test_paper_futures.py backend/tests/broker/test_paper_portfolio.py backend/tests/e2e/test_legacy_parity.py -q -p no:cacheprovider --basetemp $testBase
```

- [ ] **Step 3: Implement deterministic fills and protection simulation**

```python
class PaperPortfolioBroker(ExecutionBroker):
    async def submit(self, intent: OrderIntent) -> ExecutionResult:
        broker = self._spot if intent.product is ProductKind.SPOT else self._futures
        result = await broker.submit(intent)
        self._ledger.persist_execution(result)
        return result
```

Use exchange symbol rules for rounding, simulate taker/maker fees and configurable slippage, process partial fills deterministically in fixtures, and evaluate reduce-only TP/SL before new entries on each tick/candle.

- [ ] **Step 4: Run all broker tests and Legacy regression**

```powershell
$testBase = Join-Path $env:TEMP "pytest-goldguard-paper-brokers-green"
uv run pytest backend/tests/broker backend/tests/e2e/test_legacy_parity.py backend/tests/test_safety_guard.py -q -p no:cacheprovider --basetemp $testBase
uv run ruff check backend/goldguard/broker backend/tests/broker
uv run mypy backend/goldguard/broker
```

- [ ] **Step 5: Commit**

```powershell
git add backend/goldguard/broker backend/tests/broker backend/tests/e2e/test_legacy_parity.py
git commit -m "feat: simulate spot and isolated futures portfolios"
```

### Task 4: Account-wide cost, exposure, leverage, and sizing engine

**Files:**
- Create: `backend/goldguard/risk/costs.py`
- Create: `backend/goldguard/risk/portfolio.py`
- Modify: `backend/goldguard/risk/engine.py`
- Modify: `backend/goldguard/domain/defaults.py`
- Test: `backend/tests/risk/test_costs.py`
- Test: `backend/tests/risk/test_portfolio.py`
- Modify: `backend/tests/risk/test_engine.py`

**Interfaces:**
- `CostEstimate(gross_edge, fees, spread, slippage, funding, uncertainty_buffer, net_edge)`.
- `PortfolioRiskSnapshot` includes equity, available product balances, positions, correlation groups, rolling loss, and current exposure.
- `RiskEngine.plan_entry(opportunity, market, portfolio, profile) -> RiskDecision` returns approved/clamped margin/notional/leverage or typed HOLD reason.

- [ ] **Step 1: Write failing property and scenario tests**

```python
@given(rate=decimals(min_value="0.0001", max_value="1", places=6))
def test_approved_capital_never_exceeds_user_ceiling(rate) -> None:
    decision = plan_for_rate(Decimal(rate))
    assert decision.capital_usdt <= decision.equity_usdt * decision.max_capital_rate


def test_micro_trade_rejects_edge_below_total_cost(risk_engine) -> None:
    decision = risk_engine.plan_entry(opportunity(edge="0.0004"), costly_market(), portfolio(), micro_profile())
    assert decision.approved is False
    assert decision.reason_code == "NET_EDGE_BELOW_COST_BUFFER"
```

- [ ] **Step 2: Verify risk tests fail**

```powershell
$testBase = Join-Path $env:TEMP "pytest-goldguard-portfolio-risk-red"
uv run pytest backend/tests/risk/test_costs.py backend/tests/risk/test_portfolio.py backend/tests/risk/test_engine.py -q -p no:cacheprovider --basetemp $testBase
```

- [ ] **Step 3: Implement one risk calculation owner**

```python
@dataclass(frozen=True)
class RiskDecision:
    approved: bool
    reason_code: str
    capital_usdt: Decimal
    notional_usdt: Decimal
    leverage: int
    estimated_cost: CostEstimate
```

Apply per-trade capital, product wallet availability, total risk-adjusted notional exposure, pair/correlation concentration, volatility/liquidity, liquidation buffer, exchange filters, rolling loss, and net-edge-after-cost checks in a deterministic order with persisted inputs.

- [ ] **Step 4: Run risk/domain suites**

```powershell
$testBase = Join-Path $env:TEMP "pytest-goldguard-portfolio-risk-green"
uv run pytest backend/tests/risk backend/tests/domain -q -p no:cacheprovider --basetemp $testBase
uv run ruff check backend/goldguard/risk backend/tests/risk
uv run mypy backend/goldguard/risk
```

- [ ] **Step 5: Commit**

```powershell
git add backend/goldguard/risk backend/goldguard/domain/defaults.py backend/tests/risk backend/tests/domain
git commit -m "feat: enforce account-wide portfolio risk"
```

### Task 5: Durable per-pair coordinator and idempotent Paper intents

**Files:**
- Create: `backend/goldguard/services/execution_coordinator.py`
- Create: `backend/goldguard/storage/execution_repository.py`
- Modify: `backend/goldguard/services/coordinator.py`
- Modify: `backend/goldguard/services/runtime.py`
- Test: `backend/tests/services/test_execution_coordinator.py`
- Test: `backend/tests/storage/test_execution_repository.py`

**Interfaces:**
- `ExecutionCoordinator.evaluate(scope, candle_close) -> DecisionOutcome` acquires a durable scope lease and records one decision chain.
- `ExecutionRepository.create_intent_once(key, payload) -> tuple[OrderIntent, bool]` returns whether it was newly created.
- `ExecutionCoordinator.manage_positions(scope, quote)` is independent of entry evaluation.

- [ ] **Step 1: Write failing REST/WebSocket concurrency tests**

```python
async def test_concurrent_same_candle_creates_one_intent(coordinator) -> None:
    outcomes = await asyncio.gather(*[
        coordinator.evaluate(spot_scope("PAXGUSDT"), closed_candle()) for _ in range(10)
    ])
    assert sum(outcome.intent_created for outcome in outcomes) == 1


async def test_pause_blocks_entry_but_keeps_position_management(coordinator) -> None:
    coordinator.pause_entries()
    assert (await coordinator.evaluate(scope(), closed_candle())).action == "HOLD"
    assert (await coordinator.manage_positions(scope(), stop_quote())).action == "STOP"
```

- [ ] **Step 2: Confirm concurrency failures**

```powershell
$testBase = Join-Path $env:TEMP "pytest-goldguard-coordinator-red"
uv run pytest backend/tests/services/test_execution_coordinator.py backend/tests/storage/test_execution_repository.py -q -p no:cacheprovider --basetemp $testBase
```

- [ ] **Step 3: Implement database-backed leases and intent keys**

```python
def decision_key(mode: ExecutionMode, scope: MarketScope, close_time: datetime) -> str:
    material = f"{mode.value}|{scope.product.value}|{scope.symbol}|{close_time.isoformat()}"
    return hashlib.sha256(material.encode()).hexdigest()
```

Lock per `(mode, product, symbol)` using `worker_leases`, persist intent before broker submission, and remove the unlocked in-memory set as an authority. Duplicate callers read the persisted outcome.

- [ ] **Step 4: Run coordinator/runtime/storage suites**

```powershell
$testBase = Join-Path $env:TEMP "pytest-goldguard-coordinator-green"
uv run pytest backend/tests/services backend/tests/storage/test_execution_repository.py -q -p no:cacheprovider --basetemp $testBase
uv run ruff check backend/goldguard/services backend/goldguard/storage/execution_repository.py backend/tests/services
uv run mypy backend/goldguard/services backend/goldguard/storage/execution_repository.py
```

- [ ] **Step 5: Commit**

```powershell
git add backend/goldguard/services/execution_coordinator.py backend/goldguard/services/coordinator.py backend/goldguard/services/runtime.py backend/goldguard/storage/execution_repository.py backend/tests/services/test_execution_coordinator.py backend/tests/storage/test_execution_repository.py
git commit -m "feat: coordinate paper entries idempotently"
```

### Task 6: Rolling-loss breaker, emergency service, and multi-market runtime

**Files:**
- Create: `backend/goldguard/risk/circuit_breaker.py`
- Create: `backend/goldguard/services/emergency.py`
- Create: `backend/goldguard/services/runtime_supervisor.py`
- Modify: `backend/goldguard/services/runtime.py`
- Modify: `backend/goldguard/web/app.py`
- Test: `backend/tests/risk/test_circuit_breaker.py`
- Test: `backend/tests/services/test_emergency.py`
- Test: `backend/tests/services/test_runtime_supervisor.py`
- Test: `backend/tests/e2e/test_paper_products.py`

**Interfaces:**
- `RollingLossService.measure(now, account_scope) -> RollingLossSnapshot` includes realized, unrealized, fees, funding, and slippage.
- `EmergencyService.pause()`, `cancel_entries(scopes)`, `close_owned_positions(scopes, reason)`.
- `RuntimeSupervisor.apply_profile(profile)`, `start()`, `pause()`, `stop()`, `status()`; one child runtime per enabled scope.

- [ ] **Step 1: Write failing breaker and Paper lifecycle tests**

```python
async def test_loss_limit_cancels_entries_and_closes_owned_positions(system) -> None:
    await system.seed_loss(realized="-20", unrealized="-5", fees="2", funding="1", slippage="1")
    result = await system.breaker.evaluate(limit_usdt=Decimal("25"))
    assert result.tripped is True
    assert await system.open_entry_count() == 0
    assert await system.owned_position_count() == 0


async def test_scope_off_manages_existing_position_to_safe_exit(system) -> None:
    position = await system.open_paper_futures("BTCUSDT")
    await system.disable_scope(futures_scope("BTCUSDT"))
    assert await system.new_entries_allowed(futures_scope("BTCUSDT")) is False
    assert await system.protection_active(position.position_id) is True
```

- [ ] **Step 2: Run failure suite**

```powershell
$testBase = Join-Path $env:TEMP "pytest-goldguard-paper-runtime-red"
uv run pytest backend/tests/risk/test_circuit_breaker.py backend/tests/services/test_emergency.py backend/tests/services/test_runtime_supervisor.py backend/tests/e2e/test_paper_products.py -q -p no:cacheprovider --basetemp $testBase
```

- [ ] **Step 3: Implement background breaker and runtime ownership**

```python
class RuntimeSupervisor:
    async def start(self) -> None:
        await self._market.start(self._profile.market_scopes())
        self._tasks = {
            asyncio.create_task(self._entry_loop(), name="entry-loop"),
            asyncio.create_task(self._protection_loop(), name="protection-loop"),
            asyncio.create_task(self._breaker_loop(), name="breaker-loop"),
            asyncio.create_task(self._freshness_loop(), name="freshness-loop"),
        }
```

Breaker auto-clear requires loss aging plus fresh health/reconciliation; security or integrity blocks never auto-clear. Micro-Trade counts completed cycles in a rolling ledger query and HOLDs at 1,000.

- [ ] **Step 4: Run Gate 2 verification**

```powershell
$testBase = Join-Path $env:TEMP "pytest-goldguard-gate2"
uv run pytest backend/tests/domain backend/tests/execution backend/tests/broker backend/tests/market backend/tests/risk backend/tests/services backend/tests/e2e/test_paper_products.py -q -p no:cacheprovider --basetemp $testBase
uv run ruff check backend
uv run mypy backend/goldguard
git diff --check
```

- [ ] **Step 5: Commit**

```powershell
git add backend/goldguard/risk/circuit_breaker.py backend/goldguard/services/emergency.py backend/goldguard/services/runtime_supervisor.py backend/goldguard/services/runtime.py backend/goldguard/web/app.py backend/tests/risk/test_circuit_breaker.py backend/tests/services/test_emergency.py backend/tests/services/test_runtime_supervisor.py backend/tests/e2e/test_paper_products.py
git commit -m "feat: run protected multi-market paper trading"
```
