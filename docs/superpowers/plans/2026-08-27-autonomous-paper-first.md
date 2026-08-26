# Autonomous Paper-First GoldGuard Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the demo-only GoldGuard web runtime with an honest autonomous paper trader, bounded strategy learning, low-noise agent events, and a beginner-friendly UI.

**Architecture:** Keep the existing deterministic domain modules and introduce a focused runtime service that owns market ingestion, coordinator wiring, durable state, and event publication. The frontend consumes one typed snapshot plus SSE updates and never falls back to mock values.

**Tech Stack:** Python 3.12, FastAPI, SQLite WAL, httpx, Pydantic, React 19, TypeScript, Vitest, Playwright CLI.

**Spec:** `docs/superpowers/specs/2026-08-27-autonomous-paper-first-design.md`

## Global Constraints

- Paper trading is the only enabled execution mode for this release.
- Real-money capability remains server-gated and unavailable to the default UI.
- No fabricated market, provider, context, performance, or trade values.
- Risk limits remain deterministic and immutable at runtime.
- Displayed agent events are bounded to 30 newest items; durable ledgers remain separate.
- Every production behavior change has a failing test before implementation.

---

### Task 1: Add typed agent events and retention

**Files:**
- Create: `backend/goldguard/observability/events.py`
- Modify: `backend/goldguard/storage/schema.sql`
- Modify: `backend/goldguard/storage/repositories.py`
- Test: `backend/tests/observability/test_events.py`

**Interfaces:**
- `AgentEvent.create(action, reason, reason_codes, payload) -> AgentEvent`.
- `EventBus.publish(event) -> None` and `EventBus.recent(limit=30) -> tuple[AgentEvent, ...]`.
- `EventBus.subscribe() -> AsyncIterator[AgentEvent]` with bounded in-memory fanout.

- [ ] Write a failing test proving `recent(30)` never returns more than 30 events and removes expired routine events.
- [ ] Run `.venv/Scripts/pytest.exe backend/tests/observability/test_events.py -q` and confirm the expected missing-module failure.
- [ ] Implement the immutable event model, bounded deque, TTL filtering, and async subscriber queues.
- [ ] Add durable event serialization only for audit-worthy events; keep routine stream events memory-bounded.
- [ ] Run the focused test and the storage test suite.

### Task 2: Build a real paper trading runtime

**Files:**
- Create: `backend/goldguard/services/runtime.py`
- Modify: `backend/goldguard/services/coordinator.py`
- Modify: `backend/goldguard/web/app.py`
- Test: `backend/tests/services/test_runtime.py`

**Interfaces:**
- `TradingRuntime.start() -> None`, `pause() -> None`, `stop() -> None`, `status() -> RuntimeStatus`.
- `TradingRuntime.process_closed_candle(candle, quote) -> DecisionOutcome`.
- `TradingRuntime.process_quote(quote) -> ExitOutcome | None`.

- [ ] Write a failing integration test that starts a paper runtime, processes one closed candle, and asserts exactly one persisted decision chain.
- [ ] Run the focused test and verify it fails because the web process has no runtime service.
- [ ] Add typed async adapters for the checklist and AI veto, construct real `FeatureSnapshot` values from verified candles, and persist broker/ledger outcomes.
- [ ] Replace the random web loop with runtime start/pause/stop controls and a restart-safe halted flag.
- [ ] Run focused runtime, coordinator, broker, storage, and end-to-end tests.

### Task 3: Remove fabricated API responses and wire data sources

**Files:**
- Modify: `backend/goldguard/web/app.py`
- Modify: `backend/goldguard/market/binance.py`
- Modify: `backend/goldguard/market/history.py`
- Modify: `backend/goldguard/storage/repositories.py`
- Test: `backend/tests/web/test_api_truthfulness.py`

**Interfaces:**
- API responses return explicit `source`, `observed_at`, `stale`, and `availability` metadata.
- `/api/dashboard` returns one initial typed snapshot.
- `/api/agent/events` returns bounded recent events.
- `/api/agent/events/stream` returns SSE events.

- [ ] Write failing API tests proving flat accounts return no fabricated position, context, equity, provider, or backtest values.
- [ ] Run the tests and confirm the old fallback payloads fail the assertions.
- [ ] Remove synthetic candle generation, seeded fake reflections, hard-coded backtest fallback metrics, random provider probes, static context payloads, and representative flat-position values.
- [ ] Load verified candles and current quotes from the market client; expose degraded status when unavailable.
- [ ] Implement SSE heartbeat/reconnect-friendly output and bounded API limits.
- [ ] Run the complete backend suite and API smoke test.

### Task 4: Autonomous promotion and rollback

**Files:**
- Modify: `backend/goldguard/hermes/loop.py`
- Modify: `backend/goldguard/strategy/promotion.py`
- Create: `backend/goldguard/services/promotion_controller.py`
- Test: `backend/tests/services/test_promotion_controller.py`

**Interfaces:**
- `PromotionController.evaluate(candidate, dataset, baseline) -> PromotionDecision`.
- `PromotionController.on_canary_event(event) -> RollbackDecision | None`.

- [ ] Write failing tests for automatic promotion after all gates, rejection when risk bounds change, and rollback after a drawdown/error threshold.
- [ ] Run the focused tests and verify failure before implementation.
- [ ] Connect the existing development/validation/holdout/shadow gates without human approval for routine candidates.
- [ ] Persist candidate stage, baseline hash, canary status, rollback reason, and circuit-breaker state.
- [ ] Ensure autonomy revocation blocks research mutation and emergency stop cannot be cleared by Start.
- [ ] Run Hermes, promotion, risk, and end-to-end suites.

### Task 5: Truthful frontend state and beginner controls

**Files:**
- Modify: `frontend/src/context/BotContext.tsx`
- Modify: `frontend/src/api/client.ts`
- Modify: `frontend/src/App.tsx`
- Modify: `frontend/src/components/layout/TopHeader.tsx`
- Modify: `frontend/src/components/views/SettingsModal.tsx`
- Delete: `frontend/src/data/mockData.ts`
- Test: `frontend/src/tests/components/BotControls.test.tsx`

**Interfaces:**
- `BotContext` exposes `runtimeStatus`, `preflight`, `agentEvents`, `startPaperTrading`, `pauseTrading`, `emergencyStop`, and typed loading/error states.
- `api.getDashboard()`, `api.getAgentEvents()`, `api.streamAgentEvents()` and `api.preflight()` are the only live dashboard data paths.

- [ ] Write failing component tests for truthful flat state, start/pause labels, preflight failure, and bounded event rendering.
- [ ] Run the focused Vitest tests and confirm failure against the mock-backed context.
- [ ] Remove all production mock imports and replace silent fallbacks with loading/error/empty states.
- [ ] Add a simple paper-first start flow and keep live capability hidden/disabled.
- [ ] Add an error boundary and visible degraded connection state.
- [ ] Run all frontend unit tests, typecheck, build, and browser smoke tests.

### Task 6: Agent activity and tab completion

**Files:**
- Create: `frontend/src/components/agent/AgentActivity.tsx`
- Modify: `frontend/src/App.tsx`
- Modify: `frontend/src/components/views/MarketView.tsx`
- Modify: `frontend/src/components/views/ContextView.tsx`
- Modify: `frontend/src/components/views/DecisionsView.tsx`
- Modify: `frontend/src/components/views/TradesView.tsx`
- Modify: `frontend/src/components/strategy/StrategyStudio.tsx`
- Modify: `frontend/src/components/research/ResearchLab.tsx`
- Modify: `frontend/src/components/providers/RouteMatrix.tsx`
- Test: `frontend/src/tests/components/AllTabs.test.tsx`

**Interfaces:**
- `AgentActivity` renders the latest decision, reason, current position, and bounded event list.
- Every tab accepts typed loading/error/empty state props and has no no-op primary action.

- [ ] Write failing browser/component tests that visit every tab and assert no unhandled console errors.
- [ ] Run the tests and reproduce the current Studio crash and mobile overflow.
- [ ] Fix genome payload shape, remove no-op links/buttons, connect refresh actions, and make chart controls change real data.
- [ ] Add responsive navigation for narrow widths and the Agent tab/panel.
- [ ] Run full browser, unit, typecheck, and build verification.

### Task 7: Verified three-year dataset bootstrap and runbooks

**Files:**
- Modify: `scripts/bootstrap_history.py`
- Create: `backend/goldguard/market/dataset_service.py`
- Modify: `docs/RUNBOOK.md`
- Modify: `README.md`
- Test: `backend/tests/market/test_dataset_service.py`

**Interfaces:**
- `DatasetService.bootstrap(symbol, start, end) -> BootstrapManifest`.
- `DatasetService.status(symbol) -> DatasetStatus`.

- [ ] Write failing tests for resumable bootstrap, checksum verification, forming-candle rejection, and visible progress state.
- [ ] Run focused tests and confirm missing service behavior.
- [ ] Implement archive/API download, manifest persistence, retries/backoff and resumable progress.
- [ ] Wire backtest and runtime warmup to verified datasets instead of bootstrap randomness.
- [ ] Correct runbook commands and deployment context instructions.
- [ ] Run dataset, full backend, full frontend, and real-browser verification.

### Task 8: Deployment and final audit

**Files:**
- Modify: `docker-compose.yml`
- Modify: `docker-compose.prod.yml`
- Modify: `Dockerfile`
- Modify: `backend/Dockerfile`
- Create: `scripts/audit_release.py`
- Test: `backend/tests/e2e/test_release_audit.py`

**Interfaces:**
- `audit_release.py` reports database, market source, runtime state, event stream, frontend root, and configured safety gates.

- [ ] Write failing release-audit tests for missing Docker context, unconfigured provider, and fabricated API data.
- [ ] Run focused tests and verify failure.
- [ ] Correct build contexts and dependency-copy ordering; keep production live capability disabled.
- [ ] Add release audit checks with explicit degraded/blocked status.
- [ ] Run backend tests, frontend tests, typechecks, lint, build, browser smoke, and release audit.
- [ ] Inspect git diff and report any remaining blocked external dependency (Docker daemon, credentials, exchange account) separately.
