# GoldGuard Trading Platform Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkboxes so progress survives handoffs.

**Goal:** Deliver a paper-first PAXG/USDT trading platform with deterministic risk, bounded Gemini decisions and live context, two-year replay, an isolated Hermes research service, a polished dashboard, and a locked optional Binance Spot connector.

**Architecture:** A single FastAPI service owns facts, persistence, strategy, risk, paper execution, replay, APIs, and the bundled React UI. Binance and Gemini sit behind typed fail-closed adapters. Hermes runs as a separate official container and can submit only declarative proposals to a restricted bridge; it never receives broker or deployment credentials. SQLite is the auditable source of truth, and every order-capable transition is transactional and idempotent.

**Tech Stack:** Python 3.12, FastAPI, Pydantic 2, httpx, SQLite, pytest, Hypothesis, Ruff, mypy; React 19, TypeScript, Vite, Vitest, Testing Library, Playwright; Docker Compose; Railway; official Nous Research Hermes Agent image.

**Spec:** `docs/superpowers/specs/2026-08-26-ai-gold-trading-bot-design.md`

## Global Constraints

- Default to paper trading, long-only, one PAXG position, with no shorting, futures, leverage, transfers, deposits, or withdrawal code.
- Never expose or commit secrets. Tests use synthetic keys and fake upstream servers.
- Gemini/news/Hermes may reject entries or recommend exposure reduction; only deterministic Python may size, protect, or route an order.
- Missing, stale, contradictory, malformed, or quota-limited inputs mean `HOLD` for entries. Protective exits continue without AI.
- Historical logic is chronological, cost-aware, and free of lookahead. Untouched holdout results stay hidden until final scoring.
- No live order appears in automated verification. The live adapter requires all arming gates and a fake server in tests.
- Each task follows red-green-refactor: add a focused failing test, run it to see the expected failure, implement the smallest coherent unit, rerun, then commit.

---

### Task 1: Reproducible project skeleton and secure configuration

**Files:**
- Create: `pyproject.toml`
- Create: `.python-version`
- Create: `.env.example`
- Modify: `.gitignore`
- Create: `backend/goldguard/__init__.py`
- Create: `backend/goldguard/config.py`
- Create: `backend/tests/test_config.py`
- Create: `frontend/package.json`
- Create: `frontend/tsconfig.json`
- Create: `frontend/vite.config.ts`

- [ ] Add a failing config test proving paper mode, PAXG/USDT, 15m/1h, `/data`, and safe risk defaults are selected when optional environment values are absent.
- [ ] Run `uv run pytest backend/tests/test_config.py -q` and confirm the import/test fails for the missing package.
- [ ] Add pinned Python dependencies and a strict `Settings` model. Mark every secret with `repr=False`; reject production defaults and any enabled live mode with zero capital.
- [ ] Add frontend scripts for `dev`, `build`, `test`, `typecheck`, and `e2e`; pin package versions with an npm lockfile.
- [ ] Run `uv sync --all-extras`, `npm --prefix frontend install`, the config test, and secret-pattern checks; commit as `chore: scaffold secure GoldGuard workspace`.

### Task 2: Domain contracts, safe defaults, and professional invariants

**Files:**
- Create: `backend/goldguard/domain/enums.py`
- Create: `backend/goldguard/domain/models.py`
- Create: `backend/goldguard/domain/defaults.py`
- Create: `backend/tests/domain/test_models.py`
- Create: `backend/tests/domain/test_defaults.py`

- [ ] Write failing tests for exact-decimal money, UTC-aware timestamps, immutable Safe Default v1, long-only actions, compatible AI decisions, and complete trade plans.
- [ ] Define `BotMode`, `BotState`, `CandidateAction`, `AiDecision`, `OrderSide`, `ExitReason`, `Candle`, `FeatureSnapshot`, `TradePlan`, and versioned settings models.
- [ ] Encode hard limits: no add-to-position, no stop widening, no negative/short quantity, no market entry without stop and target, one open position, and no risk increase after losses.
- [ ] Add boundary/property tests for risk percentages, drawdown thresholds, cooldown ranges, confidence, and non-finite values.
- [ ] Run `uv run pytest backend/tests/domain -q`; commit as `feat: define safe trading domain contracts`.

The first invariant test is concrete:

```python
def test_trade_plan_rejects_stop_widening() -> None:
    plan = TradePlan(entry=Decimal("2500"), stop=Decimal("2487.50"), target=Decimal("2525"), quantity=Decimal("0.02"))
    with pytest.raises(ValueError, match="stop widening"):
        plan.with_stop(Decimal("2480"))
```

### Task 3: SQLite migrations, repositories, and immutable audit ledger

**Files:**
- Create: `backend/goldguard/storage/database.py`
- Create: `backend/goldguard/storage/schema.sql`
- Create: `backend/goldguard/storage/repositories.py`
- Create: `backend/tests/storage/test_database.py`
- Create: `backend/tests/storage/test_repositories.py`

- [ ] Write failing tests for migrations, WAL/foreign keys, immutable settings versions and paper sessions, cross-mode rejection, audit append-only behavior, unique candle decisions, and transaction rollback.
- [ ] Implement connection lifecycle and schema tables for settings, sessions, candles, context, decisions, risk, orders/fills/trades, equity, reflections, backtests, proposals, shadows, Hermes events, health, state transitions, leases, and audit.
- [ ] Store money as canonical decimal strings and timestamps as UTC ISO-8601; expose typed repository methods rather than raw SQL to routes or Hermes.
- [ ] Implement idempotency keys for candle scans, decision chains, client orders, fills, and state transitions.
- [ ] Run storage tests plus `PRAGMA integrity_check`; commit as `feat: add transactional audit ledger`.

### Task 4: Binance public market data and two-year downloader

**Files:**
- Create: `backend/goldguard/market/binance.py`
- Create: `backend/goldguard/market/history.py`
- Create: `backend/goldguard/market/quality.py`
- Create: `backend/tests/market/test_binance.py`
- Create: `backend/tests/market/test_history.py`
- Create: `backend/tests/fixtures/binance_klines.json`

- [ ] Write failing adapter tests for ping/time, exchange filters, klines, best bid/ask, pagination, retries, rate limits, and sanitized errors using `httpx.MockTransport`.
- [ ] Implement the official Binance Spot REST endpoints with explicit timeouts, bounded jittered retry, closed-candle filtering, UTC normalization, and Decimal price/quantity parsing.
- [ ] Implement a resumable downloader for two years plus at least ten warm-up days of 15m and 1h data. Deduplicate, detect gaps, hash normalized rows, and write a manifest.
- [ ] Prove a forming candle is excluded and any gap/duplicate/impossible OHLC value prevents the dataset from becoming `VERIFIED`.
- [ ] Run market tests and a public `/api/v3/ping` smoke check; commit as `feat: ingest verified Binance market history`.

### Task 5: Indicators, regime labels, and deterministic strategy v1

**Files:**
- Create: `backend/goldguard/strategy/indicators.py`
- Create: `backend/goldguard/strategy/regime.py`
- Create: `backend/goldguard/strategy/engine.py`
- Create: `backend/tests/strategy/test_indicators.py`
- Create: `backend/tests/strategy/test_engine.py`

- [ ] Add failing tests with hand-checked EMA, Wilder RSI, ATR, volume ratio, spread, and warm-up values.
- [ ] Implement pure deterministic calculations and immutable feature snapshots with quality flags.
- [ ] Add table-driven failing tests for every entry clause, regime invalidation, two closes below EMA50, duplicate candle, stale quote, and boundary equality.
- [ ] Implement strategy v1 exactly as specified: 1h trend filter and 15m pullback recovery; return structured reason codes for both candidates and `NO_ACTION`.
- [ ] Run strategy tests and snapshot the strategy version/hash; commit as `feat: implement deterministic trend pullback strategy`.

### Task 6: Deterministic risk engine and state machine

**Files:**
- Create: `backend/goldguard/risk/engine.py`
- Create: `backend/goldguard/risk/state_machine.py`
- Create: `backend/tests/risk/test_engine.py`
- Create: `backend/tests/risk/test_state_machine.py`

- [ ] Write failing property tests for ATR stop clamps, 2R target, 0.5% paper risk, cash/fee cap, exchange rounding, minimum notional, and zero/negative quantity rejection.
- [ ] Implement exact Decimal sizing and a structured approval/rejection result; reject rather than silently exceed any constraint.
- [ ] Write a full transition table test for boot, disarm, paper-ready, running, cooldown, risk/data halt, recovery, and emergency stop.
- [ ] Implement rolling 24h loss, peak drawdown, consecutive-loss cooldown, post-exit cooldown, lease/data/spread/event blocks, and restart auto-disarm.
- [ ] Run risk tests and mutation-style boundary cases; commit as `feat: enforce deterministic risk and state gates`.

### Task 7: Live cited context, macro risk, and professional checklist

**Files:**
- Create: `backend/goldguard/context/models.py`
- Create: `backend/goldguard/context/gemini_grounding.py`
- Create: `backend/goldguard/context/macro.py`
- Create: `backend/goldguard/context/playbook.py`
- Create: `backend/tests/context/test_grounding.py`
- Create: `backend/tests/context/test_playbook.py`
- Create: `backend/tests/fixtures/gemini_grounded.json`

- [ ] Write failing tests for citation extraction, timestamps, content hashing, primary-source priority, source diversity, staleness, contradictory claims, malicious web instructions, and daily request budgets.
- [ ] Implement a Gemini 2.5 Flash grounded retrieval call followed by a separate strict-schema classification call. Require citations and keep retrieved text out of every tool/order surface.
- [ ] Encode official-source prompts and risk windows for FOMC, CPI, employment, PCE/GDP and other configured high-impact events; fetch Binance system status directly.
- [ ] Implement an auditable checklist covering data/exchange health, liquidity, regime clarity, confluence, complete plan, event risk, risk budget, cooldown, and prohibited habits.
- [ ] Prove unavailable/stale/contradictory context produces entry `HOLD` while stop/target exits remain independent; commit as `feat: add cited context and professional playbook`.

The fail-closed contract is explicit:

```python
def test_uncited_breaking_claim_cannot_approve_entry() -> None:
    snapshot = ContextSnapshot(items=[ContextItem(summary="gold shock", sources=[])])
    result = ProfessionalChecklist().evaluate(snapshot=snapshot, candidate=valid_candidate())
    assert result.action is ChecklistAction.HOLD
    assert "UNCITED_CONTEXT" in result.reason_codes
```

### Task 8: Bounded Gemini decision and reflection memory

**Files:**
- Create: `backend/goldguard/ai/gemini.py`
- Create: `backend/goldguard/ai/prompts.py`
- Create: `backend/goldguard/memory/reflections.py`
- Create: `backend/tests/ai/test_gemini.py`
- Create: `backend/tests/memory/test_reflections.py`

- [ ] Write failing tests for the strict decision schema, compatibility matrix, confidence threshold, known reason codes, prompt hash, timeout/quota/refusal/malformed output, and secret redaction.
- [ ] Implement sparse candidate-only calls and fail every upstream problem to `REJECT_ENTRY`/`HOLD`; never expose quantity or broker functions.
- [ ] Write failing tests for realized outcome, MAE/MFE, fee drag, regime/context error, rule adherence, contradiction handling, and maximum three diverse memories.
- [ ] Implement immutable reflections split between historical replay and forward paper namespaces.
- [ ] Run AI/memory tests entirely against fakes; commit as `feat: bound Gemini decisions and reflection memory`.

### Task 9: Realistic paper broker and trade lifecycle

**Files:**
- Create: `backend/goldguard/broker/base.py`
- Create: `backend/goldguard/broker/paper.py`
- Create: `backend/goldguard/services/trading.py`
- Create: `backend/tests/broker/test_paper.py`
- Create: `backend/tests/services/test_trading.py`

- [ ] Write failing tests for ask/bid fills, separate spread/slippage, fees, cash reservation, exchange filters, gaps, stop-first ambiguity, target, regime exit, partial/rejected fills, and mark-to-market equity.
- [ ] Implement an atomic paper entry/protection/exit lifecycle with exactly one position and immutable paper sessions.
- [ ] Connect strategy candidate → context → Gemini → risk → broker → trade → reflection through one idempotent coordinator method.
- [ ] Prove repeated scans, worker restarts, and upstream retry cannot duplicate a decision or fill.
- [ ] Run lifecycle tests; commit as `feat: complete realistic paper trade lifecycle`.

### Task 10: Chronological replay, metrics, baselines, and reports

**Files:**
- Create: `backend/goldguard/backtest/replay.py`
- Create: `backend/goldguard/backtest/metrics.py`
- Create: `backend/goldguard/backtest/reports.py`
- Create: `backend/tests/backtest/test_replay.py`
- Create: `backend/tests/backtest/test_metrics.py`

- [ ] Write failing lookahead tests proving signals use closed bars and entries occur no earlier than the next bar.
- [ ] Implement accelerated event-time replay with cost modeling, conservative same-bar ordering, isolated accounts, cancellable progress, and reproducible run hashes.
- [ ] Implement the chronological 70/15/15 split plus walk-forward windows, keeping final holdout hidden until a frozen proposal is scored.
- [ ] Add verified metrics: net/gross return, expectancy, profit factor, Sharpe, Sortino, Calmar, drawdown, exposure, fee drag, sample sufficiency, regime stability, buy-and-hold, and deterministic baseline.
- [ ] Run tests with a hand-calculated miniature ledger; commit as `feat: add unbiased replay and performance evaluation`.

### Task 11: Isolated Hermes proposal and shadow workflow

**Files:**
- Create: `backend/goldguard/hermes/models.py`
- Create: `backend/goldguard/hermes/client.py`
- Create: `backend/goldguard/hermes/service.py`
- Create: `backend/tests/hermes/test_proposals.py`
- Create: `backend/tests/hermes/test_isolation.py`
- Create: `hermes/config.yaml`
- Create: `hermes/SOUL.md`
- Create: `hermes/skills/goldguard-research/SKILL.md`

- [ ] Write failing tests for the allowlisted strategy grammar, numeric safety bounds, parent version, evidence references, proposal immutability, replay attempts, oversized payloads, code/shell fields, and holdout embargo.
- [ ] Implement a bearer-authenticated Hermes client for `/v1/chat/completions`; parse strict proposal JSON and fail closed without affecting active trading.
- [ ] Implement proposal validation, bounded backtest requests, candidate versions, identical-input shadow accounts, and authenticated human-only activation.
- [ ] Seed Hermes with a Gemini-native profile, professional research routine, one-change-at-a-time rule, hard tool-loop stops, and persistent memory/skills under `/opt/data`.
- [ ] Prove Hermes has no broker/settings/secret endpoint or filesystem mount and cannot activate a proposal; commit as `feat: isolate Hermes research and shadow strategies`.

### Task 12: Locked Binance Spot live connector

**Files:**
- Create: `backend/goldguard/broker/binance_spot.py`
- Create: `backend/goldguard/live/arming.py`
- Create: `backend/tests/broker/test_binance_spot.py`
- Create: `backend/tests/live/test_arming.py`

- [ ] Build a fake Binance server and write failing tests for signed read-only preflight, permission checks, clock skew, symbol/account filters, reconciliation, client order IDs, uncertain responses, OCO protection, and forced exit on protection failure.
- [ ] Implement only spot-account, order, cancel, query, and OCO endpoints; explicitly reject withdrawal capability and omit every transfer/margin/futures endpoint.
- [ ] Implement independent environment, reauthentication, typed phrase, capital ceiling, permission, reconciliation, and flat-position gates; auto-disarm on restart/uncertainty/change/halt.
- [ ] Ensure the adapter is unreachable when `LIVE_CAPABILITY_ENABLED=false`, live maximum capital is zero by default, and no automated test can reach production order URLs.
- [ ] Run live tests against the fake server only; commit as `feat: add multi-gated Binance spot connector`.

### Task 13: FastAPI, authentication, coordinator, REST, and SSE

**Files:**
- Create: `backend/goldguard/main.py`
- Create: `backend/goldguard/api/auth.py`
- Create: `backend/goldguard/api/routes.py`
- Create: `backend/goldguard/api/events.py`
- Create: `backend/goldguard/services/coordinator.py`
- Create: `backend/tests/api/test_api.py`
- Create: `backend/tests/api/test_auth.py`

- [ ] Write failing API tests for first-run setup/login/logout, secure cookies, CSRF, throttling, session expiry, health/readiness, overview, candles, decisions, trades, contexts, backtests, settings, paper reset, Hermes Lab, audit, and SSE.
- [ ] Implement a single-admin Argon2 session flow; redact secrets and reject production startup with default session settings.
- [ ] Implement typed routes that call services only, never repositories or brokers directly. Audit all mutations.
- [ ] Implement one lease-owning background coordinator with graceful shutdown, periodic scan, quote protection, context refresh, daily reports, and safe loss of lease.
- [ ] Run API tests and OpenAPI validation; commit as `feat: expose authenticated trading control API`.

### Task 14: GoldGuard dashboard

**Files:**
- Create: `frontend/index.html`
- Create: `frontend/src/main.tsx`
- Create: `frontend/src/App.tsx`
- Create: `frontend/src/api.ts`
- Create: `frontend/src/styles.css`
- Create: `frontend/src/components/Shell.tsx`
- Create: `frontend/src/components/MetricCard.tsx`
- Create: `frontend/src/components/StatusPill.tsx`
- Create: `frontend/src/components/DecisionTimeline.tsx`
- Create: `frontend/src/components/ContextFeed.tsx`
- Create: `frontend/src/components/EquityChart.tsx`
- Create: `frontend/src/components/SettingsForm.tsx`
- Create: `frontend/src/pages/OverviewPage.tsx`
- Create: `frontend/src/pages/MarketPage.tsx`
- Create: `frontend/src/pages/ContextPage.tsx`
- Create: `frontend/src/pages/DecisionsPage.tsx`
- Create: `frontend/src/pages/TradesPage.tsx`
- Create: `frontend/src/pages/BacktestsPage.tsx`
- Create: `frontend/src/pages/HermesPage.tsx`
- Create: `frontend/src/pages/MemoryPage.tsx`
- Create: `frontend/src/pages/SettingsPage.tsx`
- Create: `frontend/src/pages/HealthPage.tsx`
- Create: `frontend/src/test/App.test.tsx`

- [ ] Write failing UI tests for paper/live visual distinction, health, account/equity/open-position cards, decision evidence, cited live context, settings validation, Safe Default restore, new paper session, backtest progress, Hermes proposals, and live arming gates.
- [ ] Build the approved dark graphite/gold visual system with responsive shell, keyboard navigation, loading/error/empty states, and reduced motion.
- [ ] Implement Overview, Market, Live Context, Decisions, Trades/Equity, Backtests, Hermes Lab, Memory, Settings, and Health/Audit with route-level lazy loading.
- [ ] Use SSE for new events, paginate large histories, and ensure no secret value is ever rendered or returned.
- [ ] Run Vitest, TypeScript, and production build; commit as `feat: build polished GoldGuard dashboard`.

The visible safety state is tested directly:

```tsx
it("shows paper mode and keeps live execution locked", async () => {
  render(<App api={paperApiFixture()} />);
  expect(await screen.findByText("PAPER MODE")).toBeVisible();
  expect(screen.getByRole("button", { name: "Arm live trading" })).toBeDisabled();
});
```

### Task 15: End-to-end safety tests and accessibility/performance polish

**Files:**
- Create: `frontend/playwright.config.ts`
- Create: `frontend/e2e/paper-flow.spec.ts`
- Create: `frontend/e2e/safety.spec.ts`
- Create: `backend/tests/security/test_redaction.py`

- [ ] Add browser tests for setup, login, adjustable paper balance, start/pause, deterministic backtest, evidence drill-down, Safe Default restore, responsive desktop/mobile, and restart recovery.
- [ ] Add negative tests proving a single request cannot arm live trading, Hermes cannot activate, malicious news cannot inject actions, stale inputs hold, and no withdrawal/short/add-to-loss path exists.
- [ ] Run keyboard and accessible-name checks, inspect mobile overflow, and keep the initial production bundle within the declared split targets.
- [ ] Run the combined backend/frontend/E2E suite with fake upstreams.
- [ ] Commit as `test: prove end-to-end paper flow and safety boundaries`.

### Task 16: Containerization, Railway, operations, and documentation

**Files:**
- Create: `Dockerfile`
- Create: `docker-compose.yml`
- Create: `railway.toml`
- Create: `scripts/entrypoint.sh`
- Create: `README.md`
- Create: `docs/operations.md`
- Create: `docs/live-safety.md`
- Create: `docs/data-and-models.md`

- [ ] Build a multi-stage frontend/backend image, run as non-root, persist `/data`, expose one app port, add health checks, and use graceful shutdown.
- [ ] Add the pinned official Hermes service with `gateway run`, `/opt/data`, Gemini native provider, API auth, hard tool-loop stops, no public dashboard, no shared volume, and no Binance/Railway secrets.
- [ ] Document local setup, secret rotation, model/quota limitations, two-year bootstrap, seven-day frozen forward test, backups, recovery, paper reset, live preflight, emergency disarm, and Railway browserless deployment without GitHub.
- [ ] Validate Compose/Railway files structurally when Docker/Railway CLI are unavailable; run full builds where available.
- [ ] Commit as `ops: package GoldGuard for local and Railway deployment`.

### Task 17: Real-data bootstrap, evaluation, final verification, and handoff

**Files:**
- Create: `scripts/bootstrap_history.py`
- Create: `scripts/run_backtest.py`
- Create: `data/.gitkeep`
- Create: `reports/.gitkeep`

- [ ] Fetch two full closed-candle years plus warm-up for PAXG/USDT 15m and 1h; resume safely, validate gaps, and record checksums without committing bulk market data.
- [ ] Run the deterministic baseline and cost-adjusted buy-and-hold comparison. Run Gemini/Hermes-enhanced evaluation only where time-correct context exists; label sample limitations.
- [ ] Execute `ruff`, `mypy`, all pytest suites, frontend tests/typecheck/build, E2E tests, migration/integrity checks, secret scans, public-data smoke, and container/config checks; capture exact results.
- [ ] Review the implementation against every acceptance criterion and scan for unfinished markers, hard-coded secrets, unsafe order URLs, and unhandled `float` money.
- [ ] Persist source/documentation/report deliverables, then use Railway browserless login only when the operator is available; never block local completion on cloud authentication.
- [ ] Commit as `release: verify GoldGuard paper trading platform`.

## Plan Self-Review Gate

- [ ] Every approved subsystem maps to at least one task and test: paper wallet, Safe Default, market data, strategy, news, professional routine, Gemini, risk, replay, memory, Hermes, shadowing, dashboard, live lock, persistence, auth, operations, and Railway.
- [ ] Every financial mutation has a deterministic owner and a negative safety test.
- [ ] Interfaces use the same canonical enums/models from Task 2; no duplicate action names or money types are introduced.
- [ ] A repository scan finds no unfinished marker, fake success path, plaintext secret, or unbounded autonomous strategy promotion.
- [ ] Implementation begins only after this plan passes `git diff --check` and is committed.
