# AI Gold Trading Bot - System Design

**Date:** 2026-08-26
**Status:** Approved in conversation; awaiting final file review
**Product:** GoldGuard (working name)
**Market:** Binance Spot PAXG/USDT
**Default mode:** Paper trading, long-only

## 1. Purpose

Build a complete, local-and-Railway-ready trading application for PAXG/USDT. The application combines deterministic market analysis with a narrowly bounded Gemini decision filter, the official Nous Research Hermes Agent as an isolated learning and shadow-strategy service, realistic paper execution, strict risk controls, historical evaluation, a persistent audit ledger, and a fast browser dashboard.

The system is an experimentation and execution platform, not a promise of profit or superiority over professional traders. It must make performance measurable, expose failure clearly, and fail safely. Paper mode remains the default. A Binance Spot connector is included for later real-account use, but live execution remains locked until the operator deliberately configures and arms it.

## 2. Scope

### Included

- Binance public PAXG/USDT market data through CCXT.
- Live, cited market-context collection using Gemini Google Search grounding, with source-age and conflict checks.
- Scheduled macro-event and Binance service-health risk gates.
- Completed 15-minute entry candles and 1-hour regime candles.
- Deterministic indicators and a versioned trend-pullback strategy.
- Gemini structured-output approval/rejection and early-exit filter.
- Deterministic, non-bypassable risk management.
- Realistic paper wallet, orders, fills, fees, spread, slippage, gaps, and exchange filters.
- Adjustable paper starting capital with preserved historical sessions.
- One-click, versioned Safe Default settings preset.
- Persistent SQLite ledger with migrations, WAL mode, UTC timestamps, and exact decimal money calculations.
- Backtesting, walk-forward evaluation, baseline comparison, and exportable reports.
- A reproducible two-year historical bootstrap using Binance candles, preceded by enough warm-up data for all indicators.
- Reflection memory that informs the AI but cannot rewrite strategy or risk rules.
- The official Hermes Agent with persistent memory and self-created analytical skills, isolated from execution and wallet authority.
- Versioned Hermes strategy proposals and non-executing shadow portfolios.
- Responsive React/TypeScript dashboard and FastAPI backend.
- Local Docker Compose and Railway deployment support.
- Optional Binance Spot account connection and locked live-execution adapter.
- Authentication, audit logging, health checks, backups, recovery, and comprehensive automated tests.

### Explicitly excluded from version 1

- Futures, margin, leverage, short selling, options, or borrowing.
- Self-custody wallets or decentralized-exchange routing.
- Multi-user accounts or public strategy sharing.
- Automatic hyperparameter optimization or automatic strategy rewriting.
- Claims of guaranteed returns or automatic promotion from paper to live trading.
- Withdrawal or transfer operations of any kind.

## 3. Governing Principles

1. **Python owns facts and money.** Indicators, sizing, prices, exchange constraints, fees, state transitions, and risk checks are deterministic.
2. **Gemini has bounded authority.** It can approve or reject an already-valid candidate, recommend a risk-reducing exit, and explain its reasoning. It cannot create arbitrary entries, choose quantity, change risk limits, or modify strategy code.
3. **Paper first, live locked.** A fresh install always starts in paper mode. Live trading requires several independent controls and is never enabled merely through a dashboard toggle.
4. **Every action is reproducible.** Each decision records candle timestamps, input features, strategy/config versions, model identity, prompt hash, response, checks, and resulting action.
5. **Failures reduce risk.** Missing or stale data, model failures, malformed output, database conflicts, or uncertain exchange state block new entries. Existing protective exits continue.
6. **Evaluation precedes confidence.** A seven-day run is an engineering smoke test, not evidence of an edge.
7. **Self-improvement is isolated.** Hermes may learn, create analytical skills, run experiments, and propose versions. It may not edit the executing service, change active settings, access exchange credentials, or place orders.

## 4. Architecture

The repository is a single product with separately testable frontend and backend packages.

```text
Browser dashboard
    -> FastAPI REST + event stream
        -> Bot coordinator and state machine
            -> Binance market-data adapter (CCXT)
            -> Indicator and deterministic strategy engine
            -> Gemini decision-filter adapter
            -> Deterministic risk engine
            -> Paper broker OR locked Binance live broker
            -> SQLite repositories and immutable audit ledger
        -> Backtest/evaluation service
        -> Health, backup, configuration, and report services
        -> Restricted internal research API
            <- Hermes Agent service
                -> Gemini native provider
                -> Persistent Hermes memory/skills volume
                -> Strategy proposal + shadow-evaluation workflow
```

### Runtime processes

- One FastAPI process serves the bundled frontend, API, authentication, and server-sent events.
- One in-process coordinator owns scheduled scans and price monitoring.
- A database lease prevents more than one active coordinator from acting, even if a second process starts.
- Backtests run as bounded background jobs and never share order state with live/paper sessions.
- Railway is configured for one replica and a persistent volume mounted at `/data`.
- Hermes runs as a separate Railway service and separate persistent volume. It has no mount, process, shell, database, or secret access to the trading service.

## 5. Core Components and Boundaries

### Market data adapter

- Loads Binance exchange metadata and PAXG/USDT filters.
- Fetches and normalizes OHLCV, bid/ask ticker, and server time.
- Marks candles as forming or closed; only closed candles enter indicators and decisions.
- Detects missing candles, duplicates, time drift, stale quotes, and impossible values.
- Uses retry with jitter for transient failures and a circuit breaker for sustained failures.

### Indicator engine

- Computes EMA-20 and EMA-50 on 15-minute candles.
- Computes EMA-50 and EMA-200 on 1-hour candles.
- Computes RSI-14, ATR-14, volume median/SMA, volume ratio, spread percentage, and EMA slope.
- Returns a typed immutable feature snapshot with data-quality flags.
- Requires sufficient warm-up history and never fills missing history with invented values.

### Strategy engine

- Produces deterministic `ENTRY_CANDIDATE`, `EXIT_CANDIDATE`, or `NO_ACTION` results.
- Contains no network, database, AI, or order-execution code.
- Is versioned; every decision references the exact strategy version.
- Supports a deterministic-only benchmark mode using the same candidates and exits.

### Gemini decision filter

- Accepts only typed market features, candidate context, open-position context, and up to three bounded relevant outcome summaries.
- Uses a pinned stable Gemini Flash model configured through `GEMINI_MODEL`.
- Requests strict JSON schema and validates it again with Pydantic.
- Uses deterministic settings where supported, bounded retries, a hard timeout, and prompt/response redaction.
- Converts any timeout, quota error, refusal, schema error, or low-confidence result to a safe rejection/HOLD.

The same `GEMINI_API_KEY` is used by Hermes through Hermes' native `gemini` provider. OpenRouter is not required. Core candidate calls are sparse, while Hermes research calls are scheduled and budgeted so provider exhaustion cannot affect position protection.

### Live context and news service

- Collects current gold, US-dollar, real-yield/rate, inflation, central-bank, geopolitical, PAXG, stablecoin, and Binance operational context only at a bounded cadence and when a deterministic candidate needs it.
- Uses Gemini Google Search grounding to return source URLs, publication/event timestamps, a short factual summary, affected drivers, direction, severity, and contradictions. Search-derived text is treated as untrusted data.
- Persists a content hash, citations, fetch time, event time when available, source diversity, and freshness class. Items without a timestamp or traceable source cannot create positive entry confidence.
- Separates retrieval from the trading decision. The currently available Gemini 2.5 Flash path performs a grounded retrieval call followed by a separate strict-schema decision call; raw web text never reaches order or settings tools.
- Enforces economic-event blackout windows, abnormal-volatility/spread blocks, Binance system-health checks, stale-context limits, and a daily API budget. Missing, stale, contradictory, quota-limited, or malformed context converts entry decisions to `HOLD`; it never delays stop-loss or emergency exits.
- News may veto an entry or recommend a risk-reducing exit. It cannot create a deterministic candidate, calculate size, widen protection, increase risk, or bypass the risk engine.
- Historical evaluation uses only news/event snapshots whose event time was available at each replay timestamp. If a licensed point-in-time news archive is not configured, news-enhanced results are reported only for the live-forward window and are never fabricated for the two-year replay.

### Professional operating playbook

The agent follows a versioned routine designed from reproducible professional trading disciplines rather than personality imitation:

1. **Before risk:** verify clock, feed continuity, exchange status, symbol filters, spread, liquidity, open-order reconciliation, active risk budget, scheduled high-impact events, and current gold-driver context.
2. **Classify before predicting:** label trend/range, volatility, liquidity, macro-event proximity, cross-asset agreement, and PAXG-specific basis/depeg/issuer risk. When the regime is unclear, do not trade.
3. **Demand confluence:** require the deterministic setup first, then assess live context. A compelling story without a valid setup is `HOLD`; a valid setup with severe adverse news is rejected.
4. **Plan the whole trade:** define entry, size, stop, target, invalidation, maximum holding logic, expected fees/slippage, and the exact reason to abstain before an order is permitted.
5. **Manage, do not improvise:** never average down, revenge-trade, chase a missed move, widen a stop, add leverage, or increase risk after losses. Protective exits outrank all analysis.
6. **Review evidence:** capture hypothesis versus outcome, execution quality, maximum adverse/favorable excursion, regime error, context error, and rule adherence after every close.
7. **Improve conservatively:** Hermes groups mistakes, proposes one measurable change at a time, and tests it on unseen data and shadow trading. It may learn a habit or analytical skill, but cannot promote itself or rewrite execution code.

Source priority is explicit: exchange facts from Binance; PAXG reserve/issuer facts from Paxos; scheduled US macro releases from the Federal Reserve, BLS, BEA, and US Treasury; weekly positioning from CFTC; gold demand/ETF/central-bank context from World Gold Council; and breaking-news discovery through cited Google Search grounding. Primary sources outrank commentary, multiple independent sources are preferred for breaking claims, and social-media sentiment is never sufficient to authorize a trade.

### Risk engine

- Is the only component allowed to calculate quantity, stop, target, cash use, or trading eligibility.
- Applies exchange price/quantity/notional filters and exact decimal rounding.
- Evaluates account, daily, peak-to-trough, consecutive-loss, cooldown, stale-data, spread, and live-mode constraints.
- Returns an approved order plan or a structured rejection; it never silently adjusts beyond declared clamping rules.

### Broker interface

Both brokers implement the same commands and event model: preflight, balances, positions, place entry, place protection, exit, cancel, reconcile, and health.

- `PaperBroker` uses current quotes and configured execution realism.
- `BinanceSpotBroker` uses authenticated Binance Spot APIs and remains inaccessible unless live mode is fully armed.

### Ledger and repositories

- SQLite runs in WAL mode with foreign keys, explicit transactions, migrations, and periodic integrity checks.
- Monetary/order quantities use decimal strings/integers at declared precision; floating point is limited to indicators.
- Unique constraints make candle scans, decision creation, fills, and state transitions idempotent.
- Secrets never enter the database or logs.

## 6. Bot State Machine

The coordinator has explicit states:

- `BOOTING`: load configuration, migrate database, acquire lease, and run preflight.
- `DISARMED`: dashboard and market monitoring available; no new orders.
- `PAPER_READY`: paper account is valid and eligible to run.
- `LIVE_READ_ONLY`: real account is connected for balance/preflight but execution is locked.
- `RUNNING_FLAT`: active and waiting without an open position.
- `RUNNING_OPEN`: active with one position; protection monitoring is mandatory.
- `COOLDOWN`: exits continue, but entries are temporarily blocked.
- `RISK_HALTED`: entries are blocked by a risk threshold.
- `DATA_HALTED`: entries are blocked by market-data health.
- `RECOVERY_REQUIRED`: stored state and broker state disagree; no entry until reconciliation succeeds.
- `EMERGENCY_STOPPED`: manual reset and successful preflight are required.

Every transition is validated, transactional, timestamped, and appended to the audit log. A restart always begins disarmed, reconciles state, and never replays an already-recorded candle action.

## 7. Strategy Version 1: Long-Only Trend Pullback

The initial strategy is intentionally narrow and testable. Thresholds live in the versioned preset and may be changed only by creating a new configuration version.

### Data prerequisites

- At least 210 closed 1-hour candles and 80 closed 15-minute candles.
- Latest completed candles are contiguous and recent.
- Bid and ask are valid and spread is below the configured maximum.

### Long regime

All conditions must hold:

- 1-hour EMA-50 is above EMA-200.
- Latest 1-hour close is above EMA-200.
- EMA-50 slope over the configured lookback is positive.

### Entry candidate

All conditions must hold on completed 15-minute candles:

- The previous close is at or below EMA-20 and the latest close recovers above EMA-20.
- Latest close remains above EMA-50.
- RSI-14 crosses upward through the configured recovery level and stays below the overextension ceiling.
- Volume ratio is at or above the configured minimum.
- ATR percentage is within configured minimum and maximum bounds.
- No position, cooldown, risk halt, duplicate scan, or data-quality block exists.

The Safe Default preset starts with an RSI recovery level of 45, RSI ceiling of 68, minimum volume ratio of 0.80, 15-minute ATR between 0.05% and 1.50% of price, and maximum observed spread of 0.15%. These are hypotheses to evaluate, not claims of optimality.

### Entry approval

Gemini receives the candidate only after all deterministic conditions pass. An entry requires `APPROVE_ENTRY` and confidence at or above 65. A rejected or unavailable AI response creates no order.

### Stop, target, and quantity

- Stop distance starts at 1.5 times 15-minute ATR and is clamped between 0.35% and 1.25% of entry price.
- Take-profit starts at 2.0 times initial risk (`2R`).
- Paper risk is at most 0.5% of current equity and is reduced automatically when cash exposure, exchange precision, or minimum-notional constraints prevent that size.
- Maximum usable paper cash is 95% of available quote balance, including estimated fees.
- Only one position may be open.

### Exit

- Stop-loss and take-profit always have priority.
- A deterministic regime invalidation exits at the next available price when 1-hour EMA-50 is no longer above EMA-200 or two consecutive completed 15-minute candles close below EMA-50.
- Gemini may recommend `EXIT` on a completed decision candle; because this only reduces exposure, the risk engine may accept it after data and state validation.
- Gemini cannot widen a stop, cancel protection, add to a position, or reverse short.

## 8. Gemini Contract

The response schema contains:

```json
{
  "decision": "APPROVE_ENTRY | REJECT_ENTRY | EXIT | HOLD",
  "confidence": 0,
  "reason_codes": ["string"],
  "rationale": "short string",
  "memory_refs": ["reflection-id"]
}
```

The application validates decision compatibility with the current candidate/state, confidence range, known reason codes, length limits, and memory references. Unknown keys and non-finite values are rejected. The prompt makes market text and stored reflections data, not instructions, and contains no order-placement tool.

## 9. Hermes Agent Learning and Shadow Service

The project deploys a pinned official Nous Research Hermes Agent release as a separate service. Hermes uses the native Gemini provider, persistent memory, and its normal skill-learning capability, but only inside its own isolated container and volume.

### Permitted Hermes tools

- Read sanitized closed-candle features and market-quality metadata.
- Read paper trade, decision, fee, risk, and outcome summaries.
- Query historical experiment results.
- Submit a declarative strategy proposal in a strict schema.
- Request a bounded backtest or shadow portfolio for a submitted proposal.
- Read the result of its own experiments and refine its own analytical skills/memory.

### Prohibited Hermes authority

- No Binance API key, balance, wallet, order, withdrawal, or execution tool.
- No access to the core service filesystem, database file, process, deployment token, session secret, or source repository.
- No direct settings mutation, strategy activation, risk-limit change, or live/paper order placement.
- No arbitrary query execution against the core database.
- No network route to private administrative endpoints.

Hermes communicates through a narrow internal API authenticated with a dedicated service token. Requests are schema-validated, rate-limited, size-limited, audited, and mapped to deterministic application functions. Strategy proposals are data, never executable Python or shell code.

### Proposal and shadow workflow

1. Hermes submits a declarative proposal containing indicator conditions, numeric bounds, rationale, evidence references, and parent strategy version.
2. The core validates that every field belongs to an allowlisted strategy grammar and safe parameter range.
3. The backtest service evaluates it on allowed historical partitions without revealing untouched holdout data early.
4. Passing proposals become immutable candidate versions.
5. Candidate versions run in a separate shadow paper account using live market data but place no broker orders.
6. The dashboard compares the active strategy and each shadow candidate using identical prices and execution assumptions.
7. No candidate can become active automatically. Activation requires authenticated human approval and creates a new settings/strategy version.

During the seven-day forward test, the executing Safe Default version stays frozen. Hermes may learn and produce shadow candidates, but those candidates cannot alter the seven-day baseline.

## 10. Two-Year Accelerated Replay and Evaluation Partitioning

The bootstrap fetches two complete years of Binance PAXG/USDT 15-minute and 1-hour candles plus at least 10 preceding warm-up days. The warm-up allows the two-year evaluation window to begin with a valid 1-hour EMA-200 and other rolling features.

The two-year evaluation window is partitioned chronologically:

- First 70%: development/learning data available to Hermes for analysis and proposal refinement.
- Next 15%: validation data used for candidate selection and rejection.
- Final 15%: untouched holdout data evaluated once for final historical reporting.

Raw responses are normalized, deduplicated, gap-checked, timestamped in UTC, cached, and hashed. A manifest records exchange, symbol, timeframes, requested range, actual closed-candle range, missing intervals, fetch time, and checksum. Forming candles are excluded.

Historical candles are replayed chronologically at accelerated speed. Strategy decisions and trade closures create evidence and historical reflections in event-time order; neither Hermes nor the strategy sees later candles during an event. Historical and forward-test memories remain separate. Hermes cannot inspect holdout outcomes until a proposal is frozen for final scoring. Seven live paper days then form an additional forward window; they are not merged into the historical score.

## 11. Reflection Memory

At each closed trade, Gemini compares the recorded hypothesis with realized execution and outcome. The result is stored as a structured reflection containing regime tags, entry features, adverse/favorable excursion, fee impact, outcome, and a concise lesson.

Reflection rules:

- Reflections cannot change executable settings or risk constraints.
- Retrieval is limited to three records with matching deterministic regime tags.
- Recent outcomes are diversity-filtered so one repeated loss cannot dominate the context.
- Contradictory reflections are shown together and flagged.
- The dashboard can mark a reflection accepted, rejected, or archived; all versions remain auditable.
- Evaluation reports compare results with memory enabled and disabled when sample size allows.

## 12. Paper Execution Model

- Entry market buys fill from current ask plus configurable slippage.
- Exit market sells fill from current bid minus configurable slippage.
- Default taker fee is configurable and initialized conservatively at 0.10% per fill.
- Default extra slippage is 0.02%, with observed spread treated separately.
- Exchange quantity, price, step-size, and minimum-notional filters are applied before acceptance.
- Stops are triggered using quote/tick monitoring during runtime and candle high/low during backtests.
- A gap fills at the first available price rather than the requested stop.
- If a historical candle touches both stop and target and sequence is unknowable, the stop is assumed first.
- Partial fills, rejected orders, and insufficient cash have explicit events and tests.
- Equity includes cash plus mark-to-market open PAXG at the conservative bid.

Creating or resetting paper money creates a new immutable paper session with the requested initial balance. Previous sessions, trades, and reports remain available.

## 13. Risk Controls

### Safe paper defaults

- Starting balance: 100 USDT.
- Risk per trade: maximum 0.50% of equity.
- Maximum positions: one.
- Maximum cash utilization: 95%.
- Minimum cooldown after exit: 60 minutes.
- Three consecutive losses: six-hour entry cooldown.
- Rolling 24-hour equity loss of 3%: 24-hour risk halt.
- Peak-to-trough drawdown of 5%: emergency halt requiring manual reset.
- Data staleness, excessive spread, database uncertainty, or broker uncertainty: no new entry.

### Live-mode defaults

- Live mode disabled and maximum live capital set to zero.
- When deliberately configured, default per-trade risk is 0.25%, maximum one position, a 1.50% rolling 24-hour loss halt, and a 3.00% peak-to-trough emergency halt.
- A user-supplied maximum live capital amount is mandatory and cannot exceed available quote balance.
- No leverage, margin, borrowing, or shorts.
- Any risk reduction is allowed; any risk increase requires all normal checks.

Safety-critical settings have hard validation ranges: paper risk per trade 0.05%-1.00%, live risk per trade 0.05%-0.50%, reward target 1.0R-4.0R, daily loss threshold 0.50%-3.00%, emergency drawdown threshold 1.00%-5.00%, and cooldown 15-1,440 minutes. The emergency drawdown threshold must be greater than the daily threshold. The Safe Default preset is immutable and restorable in one action. Custom changes create a new version and never rewrite the historical configuration attached to past decisions.

## 14. Binance Real-Account Connector

### Secret handling

- `BINANCE_API_KEY` and `BINANCE_API_SECRET` are supplied through `.env` locally or secret variables on Railway.
- Keys are never returned to the browser, written to SQLite, included in exception traces, or shown after entry.
- Documentation requires a dedicated API key with withdrawals disabled and recommends an IP allowlist.
- Preflight rejects an account that cannot trade spot or reports withdrawal capability.

### Arming gates

All gates must pass:

1. Server environment explicitly permits live capability.
2. Admin authentication and password re-confirmation succeed.
3. The operator types a confirmation phrase naming PAXG/USDT and the maximum capital.
4. API permissions, server time, balances, symbol status, exchange filters, and open orders reconcile.
5. The live-capital ceiling and live risk profile are valid.
6. The bot is flat or exactly reconciled with a supported existing position.

The bot auto-disarms on restart, configuration change, risk halt, repeated API uncertainty, or reconciliation failure.

### Real-order protection

- Entry quantity uses confirmed available funds and current exchange filters.
- After a confirmed market entry, the connector immediately places exchange-native protective sell orders/OCO when supported.
- If protective placement cannot be confirmed, the connector submits an immediate risk-reducing exit, raises an emergency event, and disarms.
- On restart, the connector reconciles balances, orders, fills, and protection before permitting any new entry.
- The application contains no withdrawal, deposit-address, transfer, margin, or futures endpoint.

Automated verification never places a real order. Live execution becomes testable only after the operator supplies credentials and explicitly arms it outside the test suite.

## 15. Data Model

Principal records:

- `schema_migrations`
- `users` and `sessions`
- `settings_presets` and `settings_versions`
- `bot_runs`, `worker_leases`, and `state_transitions`
- `paper_accounts` and `equity_snapshots`
- `market_candles`, `market_snapshots`, and `data_quality_events`
- `context_snapshots`, `context_sources`, and `macro_risk_windows`
- `strategy_candidates`
- `ai_decisions` and `ai_attempts`
- `risk_decisions` and `risk_events`
- `positions`, `orders`, `fills`, and `trades`
- `reflections` and `reflection_links`
- `backtest_runs`, `backtest_trades`, and `evaluation_reports`
- `historical_data_manifests`, `strategy_proposals`, `strategy_versions`, `shadow_accounts`, `shadow_runs`, and `hermes_events`
- `audit_events` and `system_health_events`

Every trading record includes `mode` (`paper` or `live`) and account/session identity. Database constraints prohibit cross-mode linkage.

## 16. Dashboard and User Experience

The frontend uses React, TypeScript, Vite, bundled assets, route-level code splitting, and a small event-stream client. It is responsive, keyboard accessible, and usable on mobile.

### Screens

- **Overview:** mode, arm state, price, account equity, realized/unrealized PnL, drawdown, active risk limits, open position, protection, and system health.
- **Market:** candlesticks, indicators, current deterministic regime, candidate status, spread, and data quality.
- **Live Context:** cited news/macro drivers, source timestamps, freshness, conflicts, active blackout windows, and the exact context attached to each decision.
- **Decisions:** chronological candidate, AI, risk, and execution evidence with reason codes.
- **Trades:** filters, fills, fees, excursions, outcomes, and CSV export.
- **Equity:** equity curve, drawdown, benchmark, and session comparison.
- **Backtests:** launch bounded historical runs, inspect progress, compare deterministic baseline and AI-filter recordings, and export reports.
- **Hermes Lab:** agent health, current model/quota state, learned analytical skills, evidence-linked proposals, validation/holdout results, and active-versus-shadow comparisons.
- **Memory:** reflections, relevance, contradictions, status, and linked trades.
- **Settings:** active version, Safe Default restore, custom settings with validation, paper-session creation, model status, and Binance connection preflight.
- **Health/Audit:** feeds, model, database, coordinator lease, recent errors, state transitions, backup/export, and recovery guidance.

Paper mode uses a calm neutral accent. Armed live mode uses an unmistakable persistent red treatment and displays the live-capital ceiling on every trading screen.

### Performance targets

- No third-party runtime CDN dependency.
- Initial route is code-split and production assets are compressed.
- Normal local API reads target sub-200 ms excluding upstream calls.
- New internal events appear in the open dashboard within one second under normal conditions.
- Charts virtualize or paginate long histories rather than loading the entire ledger.

## 17. Authentication and Security

- Single-admin first-run setup stores only an Argon2 password hash.
- Secure, HTTP-only, same-site cookies; CSRF protection on mutations; login throttling and session expiry.
- Production startup rejects an unset/default session secret or an unprotected public dashboard.
- All settings mutations and arming attempts are audited.
- User-supplied text is never treated as model/system instructions.
- Logs use structured redaction and never contain API secrets, cookies, or complete prompts containing sensitive configuration.
- Dependencies are pinned and checked during CI/local verification.
- Hermes runs with a read-only container filesystem except its dedicated memory/skills volume, a non-root user, restricted internal networking, and no trading or deployment secrets.

## 18. Backtesting and Evaluation

- Historical candles are fetched, validated, cached, and processed chronologically.
- Indicators use only information available at the decision timestamp.
- Entries execute no earlier than the next available bar/quote after a completed signal.
- Fees, spread, slippage, exchange precision, minimum notional, gaps, and conservative same-bar exit ordering are included.
- Reports include trade count, net/gross PnL, profit factor, expectancy, win/loss size, max drawdown, exposure, fee drag, consecutive losses, and regime breakdown.
- Reports also include annualized return where statistically appropriate, Sharpe ratio, Sortino ratio, downside deviation, Calmar ratio, and comparison against fee-adjusted PAXG buy-and-hold and the deterministic strategy baseline.
- Default evaluation uses chronological train/validation/test windows and separate walk-forward windows; test results are never used to tune the same configuration.
- Deterministic strategy results are the baseline. AI-filter results are compared only from recorded/replayable AI decisions or a declared model run with its exact version and cost.
- Reports flag inadequate sample size. A seven-day paper run cannot unlock live mode automatically.
- The default bootstrap report shows the 70%/15%/15% chronological partitions separately and never presents tuned validation performance as untouched performance.
- During the seven-day forward run, daily reports compare the frozen active version with Hermes shadow candidates, but no mid-run activation is permitted.
- Strategy ranking prioritizes risk-adjusted holdout and forward performance, drawdown, robustness across windows, and cost sensitivity. A higher headline return alone cannot promote a proposal.

Recommended readiness evidence is at least 100-200 closed paper/backtest trades across multiple regimes plus 60-90 days of stable paper operation. This is evidence collection, not a guarantee of future performance.

## 19. Failure Handling and Recovery

- Model unavailable: reject new entries; deterministic open-position protection continues.
- News/context unavailable, stale, uncited, or contradictory: reject new entries while deterministic protection and exits continue.
- Market data stale or discontinuous: block entries and raise `DATA_HALTED`.
- Binance public endpoint unavailable: retry within bounds, then halt new entries.
- Database write uncertainty: stop before external action unless an idempotent order intent is durably recorded.
- Paper broker conflict: transaction rollback and recovery event.
- Live order response uncertain: query by client order ID before retrying; never blindly duplicate.
- Worker lease lost: coordinator stops acting immediately.
- Restart with open paper position: rebuild from ledger and current quote.
- Restart with live exposure: remain disarmed, reconcile exchange protection, then require explicit rearm.
- Corrupt database/integrity failure: read-only recovery state with backup/restore guidance.
- Hermes unavailable, over quota, or unhealthy: trading continues with the frozen strategy and core safety controls; learning/shadow work pauses.
- Invalid or unsafe Hermes proposal: reject, audit the reason, and expose it in Hermes Lab without executing it.

## 20. Testing Strategy

Implementation follows test-driven development.

### Unit and property tests

- Indicator warm-up and known reference values.
- Closed-candle selection, gaps, duplicates, and UTC boundaries.
- Strategy conditions and boundary combinations.
- Decimal sizing, rounding, minimum notional, fees, spread, slippage, and cash caps.
- Stop/target gaps and same-candle ambiguity.
- Every circuit breaker and state transition.
- Schema rejection and AI fail-closed behavior.
- News-context freshness, citation, conflict, prompt-injection, budget, and event-blackout behavior.
- Professional-playbook invariants, including no averaging down, no chasing, no stop widening, and no entry without a complete trade plan.
- Idempotency under repeated events and restarts.

### Integration and contract tests

- CCXT and Gemini adapters against recorded fixtures/mocks.
- Grounded-retrieval and strict-decision stages against recorded fixtures, including stale and malicious web content.
- SQLite migrations, transactions, WAL behavior, backups, and restart recovery.
- Paper broker lifecycle from candidate through reflection.
- Binance live adapter with a fake exchange server, including uncertain responses and OCO failure.
- Hermes bridge with a fake agent, including schema attacks, oversized proposals, forbidden fields, replay attempts, quota failure, and service isolation.
- Authentication, CSRF, settings versioning, arming gates, and secret redaction.
- REST and event-stream contracts.

### End-to-end tests

- First-run admin setup.
- Start, pause, resume, cooldown, halt, reset, and recovery flows.
- Create an adjustable paper session without deleting prior history.
- Restore Safe Default settings.
- Run and inspect a deterministic backtest.
- Fetch/validate a fixture-sized historical bootstrap, enforce partition boundaries, and prove that Hermes cannot read holdout results early.
- Submit a Hermes proposal, validate it, run it in shadow mode, and prove it cannot activate itself or reach broker operations.
- Connect/read preflight for a mocked Binance account.
- Verify that live execution cannot be armed through any single UI/API action.
- Responsive dashboard checks at desktop and mobile widths.

### Verification commands

The project exposes stable commands for formatting, linting, Python typing, TypeScript typing, unit/integration tests, frontend production build, end-to-end tests, migration checks, Docker build, and a public-data smoke test. No completion claim is made until all applicable commands pass.

## 21. Deployment and Operations

### Local

- `.env.example` documents every setting without real secrets.
- Docker Compose starts the application with `/data` persisted locally.
- A setup wizard creates the admin account and first paper session.

### Railway

- Multi-stage Docker image bundles frontend assets into the backend image.
- Railway configuration provides health checks, one replica, persistent `/data`, graceful shutdown, and environment-variable secrets.
- A second isolated Railway service runs pinned Hermes Agent with its own persistent volume and internal-only bridge credentials.
- Startup validates volume writeability, migrations, session secret, and production authentication.

### Operations

- Health and readiness endpoints distinguish app availability from trading readiness.
- Structured logs include correlation IDs and no secrets.
- Scheduled SQLite online backup plus manual export from the dashboard.
- Audit, trades, decisions, configuration, and reports are exportable.
- The operating guide explains key rotation, backup restore, paper reset, risk-halt recovery, live preflight, and emergency disarm.

## 22. Acceptance Criteria

The build is accepted when:

1. A fresh local install can complete setup and create a configurable paper account.
2. The system ingests and validates live PAXG/USDT data without using forming candles for decisions.
3. A deterministic candidate, Gemini filter, risk decision, simulated order, position, exit, and reflection can complete end to end with a full evidence chain.
4. All declared risk limits reject boundary-violating orders and cannot be bypassed by AI output or API calls.
5. Repeated scans and process restarts do not duplicate decisions or orders.
6. Historical backtests are chronological, reproducible, and include realistic costs.
7. The responsive dashboard exposes current state and preserves old sessions when paper capital is changed.
8. Safe Default restores the complete validated settings profile in one action.
9. Binance account preflight works without exposing credentials, while live order placement remains locked by default.
10. Live mode requires every independent arming gate and auto-disarms on restart or uncertainty.
11. Automated tests, production frontend build, Docker build, migrations, and safe smoke checks pass.
12. Documentation allows the user to run locally, deploy to Railway, add the Gemini key privately, connect Binance safely, and recover from common failures.
13. The bootstrap produces a verified two-year evaluation dataset plus warm-up data and enforces the 70%/15%/15% chronological partitions.
14. Official Hermes Agent persists memory/skills across restart, uses the native Gemini provider, and can submit a validated strategy proposal.
15. Hermes cannot access trading/deployment secrets, change the active strategy, place an order, or inspect holdout results before final scoring.
16. Shadow strategies receive identical live inputs and execution assumptions while remaining fully isolated from broker execution.
17. Every entry decision records a fresh, cited context snapshot or a deliberate news-unavailable `HOLD`, and high-impact event blackouts cannot be bypassed by AI output.
18. The professional operating checklist is visible and auditable, and forbidden habits such as averaging down, chasing, stop widening, or revenge re-entry are structurally impossible.

## 23. Required User-Supplied Values

No secret is required to build or test the project. To run all external integrations later, the operator supplies:

- `GEMINI_API_KEY` from Google AI Studio.
- Optional licensed low-latency market/news credentials may be added through provider interfaces later; the default paper build uses official public sources plus Gemini Google Search grounding and clearly labels their latency.
- No OpenRouter key is required for the selected Hermes setup; Hermes uses the same Gemini key through its native provider.
- A strong application session secret and first-run admin password.
- For optional Binance read-only/live preflight: a dedicated Binance API key and secret. The key must have withdrawals disabled; live trading additionally requires spot-trading permission and explicit arming.
- Railway project/volume configuration if deploying to the cloud.

Secrets must be entered directly into local `.env` or Railway variables, never pasted into chat or committed.

## 24. Delivery Artifacts

- Backend and frontend source code.
- Database schema and migrations.
- Safe Default preset and configuration validation.
- Full automated test suites and deterministic fixtures.
- Dockerfile, Docker Compose, and Railway configuration.
- `.env.example` and setup wizard.
- User guide, architecture guide, live-safety guide, and troubleshooting guide.
- Backtest/evaluation report templates and export tools.
- Pinned Hermes service configuration, restricted research bridge, strategy proposal schema, shadow evaluator, and Hermes operating guide.
