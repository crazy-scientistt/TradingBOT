# Live Binance Execution Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement authenticated Binance Spot and USD-M Futures execution with scoped credentials, idempotent orders, partial-fill protection, continuous/startup reconciliation, and fail-closed Live integration without placing unauthorized real orders.

**Architecture:** Separate signing/transport from product adapters and orchestration. Every intent is persisted before submission, assigned a deterministic client order ID, reconciled after uncertainty, protected exchange-side as fills arrive, and matched to explicit application ownership.

**Tech Stack:** Python 3.12, httpx, HMAC-SHA256, asyncio, Binance Spot and USD-M REST/WebSocket contracts, SQLite/WAL, pytest fake transports, Hypothesis, Ruff, mypy strict.

**Spec:** `docs/superpowers/specs/2026-08-28-autonomous-hermes-trading-platform-design.md`

## Global Constraints

- Automated tests use fake HTTP/WebSocket servers and fixtures; they never use real trading credentials.
- Live adapters are unreachable unless authenticated arming, Paper qualification, capability, permissions, route health, reconciliation, and protection gates pass.
- API keys require read and selected Spot/Futures trade permissions only; withdrawals/transfers disabled.
- Spot is cash-only; Futures is isolated One-way Mode.
- On timeout, query Binance by client order ID before retrying; never guess whether an order filled.
- Unknown manual/external orders or positions are not adopted, canceled, or closed.

---

### Task 1: Signed Binance transport and read-only account preflight

**Files:**
- Create: `backend/goldguard/exchange/__init__.py`
- Create: `backend/goldguard/exchange/binance_transport.py`
- Create: `backend/goldguard/exchange/binance_models.py`
- Create: `backend/goldguard/live/binance_preflight.py`
- Modify: `backend/goldguard/config.py`
- Test: `backend/tests/exchange/test_binance_transport.py`
- Test: `backend/tests/live/test_binance_preflight.py`

**Interfaces:**
- `BinanceTransport.request(product, method, path, params, signed) -> object`.
- `BinancePreflight.run(profile) -> BinancePreflightReport` checks server time, credentials, permissions, withdrawal/transfer prohibition, wallet balances, position mode, existing orders/positions, and selected symbols.
- Secrets are `SecretStr`, redacted from requests/errors/representations.

- [ ] **Step 1: Write failing signature, clock, and redaction tests**

```python
async def test_signed_request_uses_server_adjusted_timestamp(fake_binance, transport) -> None:
    await transport.request(ProductKind.SPOT, "GET", "/api/v3/account", {}, signed=True)
    assert fake_binance.last_query["timestamp"] == "1724832000123"
    assert fake_binance.signature_valid is True


def test_transport_error_redacts_api_secret() -> None:
    error = BinanceAuthenticationError("secret-value", response_body="secret-value")
    assert "secret-value" not in str(error)
```

- [ ] **Step 2: Verify missing transport fails**

```powershell
$testBase = Join-Path $env:TEMP "pytest-goldguard-binance-transport-red"
uv run pytest backend/tests/exchange/test_binance_transport.py backend/tests/live/test_binance_preflight.py -q -p no:cacheprovider --basetemp $testBase
```

- [ ] **Step 3: Implement bounded signed transport and permission report**

```python
def sign_query(params: Mapping[str, str], secret: SecretStr) -> str:
    query = urlencode(sorted(params.items()))
    return hmac.new(secret.get_secret_value().encode(), query.encode(), hashlib.sha256).hexdigest()
```

Use separate Spot/Futures base URLs, connection/read/write/pool timeouts, server-time offset, bounded retry only for safe reads, typed Binance error mapping, response-size limits, and structured request IDs. Preflight performs reads only.

- [ ] **Step 4: Run exchange/live security checks**

```powershell
$testBase = Join-Path $env:TEMP "pytest-goldguard-binance-transport-green"
uv run pytest backend/tests/exchange/test_binance_transport.py backend/tests/live/test_binance_preflight.py backend/tests/security/test_boundaries.py -q -p no:cacheprovider --basetemp $testBase
uv run ruff check backend/goldguard/exchange backend/goldguard/live/binance_preflight.py backend/tests/exchange
uv run mypy backend/goldguard/exchange backend/goldguard/live/binance_preflight.py
```

- [ ] **Step 5: Commit**

```powershell
git add backend/goldguard/exchange backend/goldguard/live/binance_preflight.py backend/goldguard/config.py backend/tests/exchange backend/tests/live/test_binance_preflight.py
git commit -m "feat: preflight signed binance accounts"
```

### Task 2: Binance Spot live broker

**Files:**
- Create: `backend/goldguard/broker/binance_spot.py`
- Modify: `backend/goldguard/broker/__init__.py`
- Test: `backend/tests/broker/test_binance_spot.py`

**Interfaces:**
- Implements `ExecutionBroker` for Spot.
- Converts `OrderIntent` to Binance symbol/side/type/quantity/quoteOrderQty/timeInForce/newClientOrderId.
- Queries/cancels by client order ID and normalizes order/fill/commission state.

- [ ] **Step 1: Write failing order precision and uncertainty tests**

```python
async def test_spot_order_respects_step_and_min_notional(broker) -> None:
    result = await broker.submit(spot_intent(quantity="0.001234", price="5000"))
    assert result.order.quantity == Decimal("0.0012")


async def test_timeout_queries_before_retry(broker, fake_binance) -> None:
    fake_binance.timeout_after_accepting("gg-spot-1")
    result = await broker.submit(spot_intent(client_order_id="gg-spot-1"))
    assert result.order.exchange_order_id == fake_binance.accepted_order_id
    assert fake_binance.post_count == 1
```

- [ ] **Step 2: Run failing Spot tests**

```powershell
$testBase = Join-Path $env:TEMP "pytest-goldguard-live-spot-red"
uv run pytest backend/tests/broker/test_binance_spot.py -q -p no:cacheprovider --basetemp $testBase
```

- [ ] **Step 3: Implement Spot adapter and normalization**

```python
class BinanceSpotBroker(ExecutionBroker):
    async def submit(self, intent: OrderIntent) -> ExecutionResult:
        persisted = self._repository.require_intent(intent.intent_id)
        try:
            payload = await self._transport.request(
                ProductKind.SPOT, "POST", "/api/v3/order", self._params(persisted), signed=True
            )
        except BinanceOutcomeUnknown:
            payload = await self._query_by_client_id(persisted.client_order_id)
        return self._normalizer.execution_result(payload, persisted)
```

Reject margin endpoints, quote borrowing, unsupported order types, and quantities outside the persisted risk-approved intent.

- [ ] **Step 4: Run Spot and execution-contract suites**

```powershell
$testBase = Join-Path $env:TEMP "pytest-goldguard-live-spot-green"
uv run pytest backend/tests/broker/test_binance_spot.py backend/tests/execution backend/tests/storage/test_execution_repository.py -q -p no:cacheprovider --basetemp $testBase
uv run ruff check backend/goldguard/broker/binance_spot.py backend/tests/broker/test_binance_spot.py
uv run mypy backend/goldguard/broker/binance_spot.py
```

- [ ] **Step 5: Commit**

```powershell
git add backend/goldguard/broker/binance_spot.py backend/goldguard/broker/__init__.py backend/tests/broker/test_binance_spot.py
git commit -m "feat: execute cash-only binance spot orders"
```

### Task 3: Binance USD-M isolated Futures live broker

**Files:**
- Create: `backend/goldguard/broker/binance_futures.py`
- Test: `backend/tests/broker/test_binance_futures.py`

**Interfaces:**
- Implements `ExecutionBroker` for USD-M Futures.
- Before entry, verifies One-way Mode, sets isolated margin for the selected symbol, and sets the deterministic approved leverage at or below the profile/exchange ceiling.
- All close/protection orders are reduce-only and cannot flip a position.

- [ ] **Step 1: Write failing isolated/leverage/reduce-only tests**

```python
async def test_futures_configures_isolated_and_approved_leverage(broker, fake_binance) -> None:
    await broker.submit(futures_intent(symbol="BTCUSDT", leverage=4))
    assert fake_binance.margin_mode("BTCUSDT") == "ISOLATED"
    assert fake_binance.leverage("BTCUSDT") == 4


async def test_close_order_is_reduce_only(broker, fake_binance) -> None:
    await broker.close("position-1", ExitReason.STOP_LOSS)
    assert fake_binance.last_order["reduceOnly"] == "true"
```

- [ ] **Step 2: Run failing Futures tests**

```powershell
$testBase = Join-Path $env:TEMP "pytest-goldguard-live-futures-red"
uv run pytest backend/tests/broker/test_binance_futures.py -q -p no:cacheprovider --basetemp $testBase
```

- [ ] **Step 3: Implement USD-M adapter**

```python
await self._ensure_one_way_mode()
await self._ensure_isolated(intent.symbol)
await self._set_leverage(intent.symbol, intent.leverage)
payload = await self._transport.request(
    ProductKind.FUTURES, "POST", "/fapi/v1/order", self._params(intent), signed=True
)
```

Normalize position risk, mark price, liquidation estimate, initial/maintenance margin, realized/unrealized P&L, commissions, and funding. Reject hedge/cross states and leverage drift.

- [ ] **Step 4: Run Futures/execution/risk suites**

```powershell
$testBase = Join-Path $env:TEMP "pytest-goldguard-live-futures-green"
uv run pytest backend/tests/broker/test_binance_futures.py backend/tests/execution backend/tests/risk -q -p no:cacheprovider --basetemp $testBase
uv run ruff check backend/goldguard/broker/binance_futures.py backend/tests/broker/test_binance_futures.py
uv run mypy backend/goldguard/broker/binance_futures.py
```

- [ ] **Step 5: Commit**

```powershell
git add backend/goldguard/broker/binance_futures.py backend/tests/broker/test_binance_futures.py
git commit -m "feat: execute isolated usd-m futures orders"
```

### Task 4: Partial-fill manager and exchange-native protection

**Files:**
- Create: `backend/goldguard/execution/order_manager.py`
- Create: `backend/goldguard/execution/protection.py`
- Modify: `backend/goldguard/storage/execution_repository.py`
- Test: `backend/tests/execution/test_order_manager.py`
- Test: `backend/tests/execution/test_protection.py`

**Interfaces:**
- `OrderManager.submit(intent) -> ManagedExecution`; consumes REST and user-data-stream updates idempotently.
- `ProtectionService.ensure(position, plan) -> ProtectionState` installs/updates exchange-side protection for filled quantity.
- Protection failure triggers immediate cancel of remaining entry and safe reduce/close of filled exposure.

- [ ] **Step 1: Write failing partial-fill/protection tests**

```python
async def test_each_partial_fill_is_protected_once(manager, fake_exchange) -> None:
    await manager.on_update(partial_fill("gg-1", filled="0.4"))
    await manager.on_update(partial_fill("gg-1", filled="0.4"))
    assert fake_exchange.protected_quantity("gg-1") == Decimal("0.4")


async def test_failed_protection_forces_exit(manager, fake_exchange) -> None:
    fake_exchange.fail_next_protection()
    result = await manager.on_update(partial_fill("gg-2", filled="1"))
    assert result.status == ManagedStatus.FORCED_EXIT
    assert fake_exchange.position_quantity("gg-2") == Decimal("0")
```

- [ ] **Step 2: Verify failures**

```powershell
$testBase = Join-Path $env:TEMP "pytest-goldguard-order-manager-red"
uv run pytest backend/tests/execution/test_order_manager.py backend/tests/execution/test_protection.py -q -p no:cacheprovider --basetemp $testBase
```

- [ ] **Step 3: Implement cumulative-fill idempotency and protection ownership**

```python
async def on_update(self, update: ExchangeOrderUpdate) -> ManagedExecution:
    delta = self._repository.record_cumulative_fill_once(update)
    if delta > 0:
        await self._protection.ensure(self._repository.position(update.intent_id), update.plan)
    return self._repository.managed_execution(update.intent_id)
```

Link TP/SL/reduce-only orders to the owned position and prevent Cancel All from removing required protection.

- [ ] **Step 4: Run execution/broker suites**

```powershell
$testBase = Join-Path $env:TEMP "pytest-goldguard-order-manager-green"
uv run pytest backend/tests/execution backend/tests/broker/test_binance_spot.py backend/tests/broker/test_binance_futures.py -q -p no:cacheprovider --basetemp $testBase
uv run ruff check backend/goldguard/execution backend/tests/execution
uv run mypy backend/goldguard/execution
```

- [ ] **Step 5: Commit**

```powershell
git add backend/goldguard/execution/order_manager.py backend/goldguard/execution/protection.py backend/goldguard/storage/execution_repository.py backend/tests/execution/test_order_manager.py backend/tests/execution/test_protection.py
git commit -m "feat: protect partial live fills idempotently"
```

### Task 5: Continuous and startup reconciliation

**Files:**
- Create: `backend/goldguard/live/reconciliation.py`
- Create: `backend/goldguard/services/reconciliation_supervisor.py`
- Modify: `backend/goldguard/live/arming.py`
- Test: `backend/tests/live/test_reconciliation.py`
- Test: `backend/tests/services/test_reconciliation_supervisor.py`

**Interfaces:**
- `ReconciliationService.reconcile(profile, reason) -> ReconciliationReport` compares exchange balances, positions, orders, recent fills, protection, and ledger ownership.
- `ReconciliationSupervisor` handles startup, user-data gaps, periodic REST snapshots, and reconnects.
- Only a clean report can transition `armed_pending_reconciliation -> armed_ready`.

- [ ] **Step 1: Write failing mismatch/repair tests**

```python
async def test_unknown_external_position_blocks_without_closing(service) -> None:
    report = await service.reconcile(profile(), "startup")
    assert "UNKNOWN_EXTERNAL_POSITION" in report.blockers
    assert service.exchange.close_calls == []


async def test_missing_owned_stop_is_repaired_before_ready(service) -> None:
    report = await service.reconcile(profile(), "restart")
    assert report.repaired == ("MISSING_STOP:position-1",)
    assert report.ready is True
```

- [ ] **Step 2: Verify failures**

```powershell
$testBase = Join-Path $env:TEMP "pytest-goldguard-reconciliation-red"
uv run pytest backend/tests/live/test_reconciliation.py backend/tests/services/test_reconciliation_supervisor.py -q -p no:cacheprovider --basetemp $testBase
```

- [ ] **Step 3: Implement authoritative reconciliation sequence**

```python
async def startup_reconcile(self) -> ReconciliationReport:
    self._arming.mark_pending("startup")
    report = await self._service.reconcile(self._profiles.active().profile, "startup")
    self._arming.apply_reconciliation(report)
    return report
```

Match by client order IDs/exchange IDs, import completed owned fills, repair protection only without increasing risk, recalculate exposure/loss, and persist every mismatch/repair/blocker.

- [ ] **Step 4: Run reconciliation/live suites**

```powershell
$testBase = Join-Path $env:TEMP "pytest-goldguard-reconciliation-green"
uv run pytest backend/tests/live backend/tests/services/test_reconciliation_supervisor.py backend/tests/execution -q -p no:cacheprovider --basetemp $testBase
uv run ruff check backend/goldguard/live backend/goldguard/services/reconciliation_supervisor.py backend/tests/live
uv run mypy backend/goldguard/live backend/goldguard/services/reconciliation_supervisor.py
```

- [ ] **Step 5: Commit**

```powershell
git add backend/goldguard/live/reconciliation.py backend/goldguard/services/reconciliation_supervisor.py backend/goldguard/live/arming.py backend/tests/live/test_reconciliation.py backend/tests/services/test_reconciliation_supervisor.py
git commit -m "feat: reconcile binance before live entries"
```

### Task 6: Live broker factory, runtime integration, and hard Live isolation tests

**Files:**
- Create: `backend/goldguard/broker/factory.py`
- Create: `backend/goldguard/live/canary.py`
- Modify: `backend/goldguard/services/runtime_supervisor.py`
- Modify: `backend/goldguard/services/emergency.py`
- Modify: `backend/goldguard/services/preflight.py`
- Modify: `backend/goldguard/web/app.py`
- Test: `backend/tests/live/test_runtime_integration.py`
- Test: `backend/tests/live/test_canary.py`
- Test: `backend/tests/security/test_live_isolation.py`
- Test: `backend/tests/e2e/test_live_fake_exchange.py`

**Interfaces:**
- `BrokerFactory.for_profile(profile, arming_state) -> ExecutionBroker` returns Paper or Live broker only after gates.
- `CanaryAllocationPolicy.allocation(genome_id, symbol_rules, evidence) -> CanaryAllocation` starts at the smallest exchange-valid amount inside all risk ceilings and advances only through bounded evidence-backed stages.
- Live runtime starts protection/reconciliation/user-data supervisors before enabling entry evaluation.
- Pause, Cancel All, Close All operate only on application-owned scopes and require the Gate 1 security dependencies.

- [ ] **Step 1: Write failing unreachable/sequence tests**

```python
@pytest.mark.parametrize("gate", ["capability", "armed", "qualified", "reconciled", "protected"])
def test_live_broker_unreachable_when_gate_fails(factory, gate) -> None:
    with pytest.raises(LiveExecutionUnavailable, match=gate):
        factory.for_profile(live_profile(), state_with_failed_gate(gate))


async def test_fake_live_start_reconciles_before_first_submit(system) -> None:
    await system.start_live_against_fake_exchange()
    assert system.events.index("reconciliation_ready") < system.events.index("entry_enabled")


def test_first_live_canary_uses_smallest_valid_risk(canary_policy) -> None:
    allocation = canary_policy.allocation("candidate-1", symbol_rules(min_notional="5"), qualified_evidence())
    assert allocation.stage == 1
    assert allocation.notional_usdt == Decimal("5")


def test_canary_cannot_scale_without_fresh_cost_adjusted_evidence(canary_policy) -> None:
    allocation = canary_policy.allocation("candidate-1", symbol_rules(), stale_canary_evidence())
    assert allocation.scale_allowed is False
```

- [ ] **Step 2: Verify integration tests fail**

```powershell
$testBase = Join-Path $env:TEMP "pytest-goldguard-live-integration-red"
uv run pytest backend/tests/live/test_runtime_integration.py backend/tests/live/test_canary.py backend/tests/security/test_live_isolation.py backend/tests/e2e/test_live_fake_exchange.py -q -p no:cacheprovider --basetemp $testBase
```

- [ ] **Step 3: Integrate broker selection without a cosmetic Live mode**

```python
def for_profile(self, profile: AutonomousProfile, state: ArmingState) -> ExecutionBroker:
    if profile.execution_mode is ExecutionMode.PAPER:
        return self._paper
    state.require_entry_ready()
    return self._live_portfolio
```

Remove metadata-only Live reporting. Every UI/API Live label must derive from the active broker mode and durable arming/reconciliation state.

`CanaryAllocationPolicy` stores stages per genome/product/pair, clamps each stage through the portfolio risk engine, requires fresh net expectancy/execution/protection evidence, and sends any breach to deterministic rollback/quarantine before another entry.

- [ ] **Step 4: Run Gate 5 verification**

```powershell
$testBase = Join-Path $env:TEMP "pytest-goldguard-gate5"
uv run pytest backend/tests/exchange backend/tests/broker backend/tests/execution backend/tests/live backend/tests/security backend/tests/services/test_reconciliation_supervisor.py backend/tests/e2e/test_live_fake_exchange.py -q -p no:cacheprovider --basetemp $testBase
uv run ruff check backend
uv run mypy backend/goldguard
git diff --check
```

Expected: all tests use fakes/fixtures and exit `0`; command output contains no key and no real Binance order ID.

- [ ] **Step 5: Commit**

```powershell
git add backend/goldguard/broker/factory.py backend/goldguard/live/canary.py backend/goldguard/services/runtime_supervisor.py backend/goldguard/services/emergency.py backend/goldguard/services/preflight.py backend/goldguard/web/app.py backend/tests/live/test_runtime_integration.py backend/tests/live/test_canary.py backend/tests/security/test_live_isolation.py backend/tests/e2e/test_live_fake_exchange.py
git commit -m "feat: integrate gated live binance execution"
```
