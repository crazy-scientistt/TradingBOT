# Autonomous Hermes Trading Platform Design

**Status:** Approved by the user on 2026-08-28

**Source baseline:** GitHub `main` at `c899c35e08ec8975766a14914d99b901501300ee`

**Execution target:** isolated local clone, then user-controlled GitHub and Railway deployment
**Supersedes:** product and architecture decisions in `2026-08-27-autonomous-paper-first-design.md`. That historical document remains in the repository for traceability.

## 1. Purpose

GoldGuard will become a persistent, fully autonomous trading platform for a non-professional user. After a one-time setup, the user chooses Paper or Live, enables Binance Spot and/or Binance USD-M Futures, selects eligible pairs, sets hard account-level risk ceilings, configures notifications, and starts autonomous trading. The system then monitors markets, researches context, creates and qualifies strategies, chooses opportunities, manages positions, learns from outcomes, and reports its work without routine user intervention.

Autonomy does not mean unlimited authority. Hermes is the strategy researcher and learner. Antigravity-hosted AI models provide Hermes's reasoning through OpenCodex. Deterministic GoldGuard code owns credentials, market/account truth, risk validation, order execution, reconciliation, safety controls, and every irreversible side effect.

This design does not promise profit. Markets can gap, liquidity can disappear, models can be wrong, and exchanges can fail. The product objective is correct autonomous operation, bounded loss exposure, honest observability, evidence-based learning, and cost-adjusted positive expectancy before any strategy becomes eligible for Live trading.

### 1.1 Current audited baseline

This document is a future implementation contract, not a description of current readiness. The source baseline at `c899c35` is an automated Paper-trading prototype with useful strategy, risk, provider, research, and dashboard foundations, but it does not yet satisfy this design:

- production startup always constructs `PaperBroker`; the existing `live` value can change displayed metadata but cannot place a real Binance order;
- execution is effectively long-only `PAXGUSDT` Spot Paper trading; USD-M Futures and multi-pair execution do not exist;
- Hermes work is performed by in-process workers/proposal helpers rather than a proven separate Hermes Agent service, and some context/Hermes paths ignore selected provider routes in favour of hard-coded model defaults;
- GoldGuard still has a direct provider-key configuration path; provider credentials have not yet been fully moved behind the approved OpenCodex-only boundary;
- automatic canary rollback depends on API/UI reads instead of an independent worker, and the autonomy-promotion flag is not consistently authoritative;
- there is no independent stale-quote watchdog, full Binance restart reconciliation, transactional per-pair execution lock, or Live order idempotency path;
- the rolling-loss implementation does not yet combine realized/unrealized P&L, fees, funding, and measured slippage or close/reduce positions as specified;
- current Settings and dashboard surfaces do not provide the approved product/pair/risk profile, Telegram, Live arming, reconciliation, or backup controls;
- some current UI states can label stale/null feeds as verified/live, render unavailable quotas as numeric defaults, or show fallback news as current; these are truthfulness defects, not acceptable degraded behaviour;
- application mutations do not yet have the required admin authentication, TOTP 2FA, CSRF boundary, or restrictive production CORS;
- current qualification thresholds and slippage evidence are materially weaker than this specification;
- Railway persistence, separate Hermes service operation, backup/restore, fault injection, all-tab browser verification, and end-to-end Live safety are unproven.

Every item above is unfinished scope. It must remain reported as unavailable or incomplete until running evidence satisfies the corresponding acceptance gate.

## 2. Locked product decisions

### 2.1 Modes and products

- Preserve the current strategy and behaviour as a distinct **Legacy** strategy mode.
- Add a distinct **Autonomous** mode; it must not silently alter Legacy rules or historical records.
- Support both **Paper** and **Live** execution from the application. Railway variables do not act as the routine Paper/Live switch.
- Support **Binance Spot** for `PAXGUSDT` gold trading. Spot is cash-only: no leverage, borrowing, or margin debt.
- Support **Binance USD-M Futures** for user-selected validated crypto perpetual pairs, initially including `BTCUSDT`, `ETHUSDT`, and `SOLUSDT` when Binance reports them tradable.
- Futures use **isolated margin only**. Cross margin is not allowed.
- Futures use Binance **One-way Mode** for this release; simultaneous long and short positions on the same pair are not supported. A conflicting account position mode blocks Futures readiness with corrective guidance.
- Binance Options contracts are out of scope. In the user's terminology, the second leveraged product is USD-M Futures.
- Non-Binance stocks, forex, commodities, and other assets may appear in research/watchlists later, but are not execution venues in this release.
- Spot and Futures switches can be enabled independently or together. The engine trades only enabled products and selected pairs.

### 2.2 Autonomy contract

When Autonomous trading is running, the system may independently choose:

- whether to trade or hold;
- which enabled pair and product has the best qualified opportunity;
- long or short direction for Futures, and buy/hold/sell actions for Spot;
- strategy, setup, chart timeframes, entry timing, order type, holding period, and exit timing;
- actual capital allocation and, for Futures, leverage at or below user ceilings;
- TP, SL, trailing/invalidation behaviour, and profit protection;
- research priorities, post-trade lessons, candidate strategies, promotion, rollback, and quarantine.

The system may not independently:

- enable Live, a product, or a pair;
- exceed a user risk ceiling;
- change credentials, withdrawal permissions, notification destinations, or security settings;
- use cross margin, borrow Spot assets, average down, use martingale/loss-recovery sizing, or widen protection beyond validated limits;
- execute generated source code, shell commands, or arbitrary strategy expressions;
- bypass Paper qualification, evidence, data-quality, reconciliation, or health gates;
- withdraw or transfer funds.

Continuous operation means continuous monitoring, research, learning, and position management. It does not create a trade quota. The correct autonomous decision can be `HOLD` for hours or days.

### 2.3 Optional Micro-Trade profile

Autonomous mode includes a separate **Micro-Trade** strategy profile. It does not replace or modify Legacy logic.

- The profile seeks many short-duration, small-risk opportunities in enabled Spot and/or Futures markets.
- `1,000` completed position cycles per rolling 24 hours is an absolute ceiling, not a target or success metric.
- The engine opens no trade solely to increase frequency.
- Expected edge must exceed estimated commissions, spread, slippage, funding, and a deterministic uncertainty buffer before entry.
- Binance minimum notional, quantity precision, rate limits, liquidity, and risk limits can lower achievable frequency.
- Performance is judged by net expectancy, drawdown, execution quality, and risk-adjusted return—not raw trade count or win rate.

## 3. System architecture

The repository deploys three isolated services with well-defined authority.

```text
User browser / Telegram
          |
          v
GoldGuard App Core ----------------------> Binance APIs
  market/account truth                      public + authenticated
  strategies and paper simulator
  deterministic risk and execution
  ledger, settings, API, dashboard
          |
          | sanitized research/tools only
          v
Hermes Agent ----------------------------> OpenCodex Gateway
  research loop, memory, reflection          provider auth + routing
  candidate strategy authoring                       |
                                                    v
                                      Antigravity AI models
```

### 3.1 GoldGuard App Core

GoldGuard owns:

- Binance market, symbol, account, order, fill, position, balance, funding, and fee truth;
- Paper Spot and Paper Futures simulation;
- Live Spot and Live Futures broker adapters;
- strategy-genome parsing and deterministic interpretation;
- risk, exposure, leverage, sizing, TP/SL validation, circuit breakers, and emergency exits;
- order idempotency, exchange reconciliation, and recovery;
- settings, authentication, 2FA, audit events, qualification reports, and durable ledgers;
- the application API, responsive dashboard, diagnostics, and Telegram delivery.

The core is the only service with Binance credentials. It does not send secrets to Hermes, OpenCodex, the browser, logs, prompts, or Telegram.

### 3.2 Hermes Agent

The actual Hermes Agent service—not only the current in-process proposal helper—owns:

- scheduled and opportunity-triggered research;
- chart/regime hypotheses and evidence synthesis;
- trade and rejected-decision postmortems;
- structured episodic memory and reusable lessons;
- bounded declarative strategy-genome proposals;
- interpretation of deterministic backtest, shadow, and canary reports;
- proposing refinements after mistakes or regime drift.

Implementation integrates the prebuilt Hermes Agent and its existing agent loop/memory capabilities. GoldGuard supplies trading-specific sanitized tools, schemas, evaluators, and safety gates; it does not rebuild a competing general agent framework from scratch.

Hermes receives a narrow authenticated tool surface containing sanitized candles/features, cited evidence, redacted trade outcomes, evaluation reports, and candidate-submission responses. It receives no broker client, Binance key, settings mutation, provider credential, shell, arbitrary filesystem access, or sealed-holdout access.

### 3.3 OpenCodex and Antigravity

OpenCodex is the sole AI-provider gateway and provider-auth owner.

```text
Hermes -> private OpenCodex API -> Antigravity provider authentication -> selected model
```

- Hermes uses an Antigravity model as its reasoning brain through the OpenCodex `hermes` route.
- Decision-veto and research-context roles may use the same model or separately selected models from the live OpenCodex catalog.
- Route selection must be honoured by every production worker; no worker may retain a hard-coded model that ignores Settings.
- Antigravity credentials persist only in OpenCodex's isolated volume. GoldGuard and Hermes know only their private service tokens.
- Existing direct Gemini/Antigravity provider-key paths in GoldGuard are removed or migrated; provider credentials cannot remain in the trading core.
- A laptop Google session is not assumed to exist on Railway. Railway requires a server-valid OpenCodex provider-account import or credential flow stored in its own persistent volume.
- Provider authentication, model availability, quota status, and restart persistence must be proven by diagnostics before AI-dependent entries are permitted.
- The OpenCodex data plane remains private. Any provider-account administration surface is strongly authenticated and exposed only for deliberate setup/maintenance, never as an unprotected public dashboard.

### 3.4 Local and Railway isolation

Local development uses the separate `TradingBOT-Autonomous` clone with unique service names, network, host ports, database path/volume, OpenCodex home, and Hermes memory volume. It must not reuse or mutate the existing `TradingBOT` checkout, its containers, databases, ports, OpenCodex home, or Hermes state.

Railway runs:

1. one public GoldGuard application service;
2. one private OpenCodex service with a persistent provider-auth/configuration volume;
3. one private Hermes service with a persistent memory volume.

The GoldGuard ledger uses a durable volume and a single-writer application instance. Health checks distinguish process liveness from trading readiness. A service can be alive while new entries remain blocked.

## 4. Authority and safety boundary

| Capability | GoldGuard deterministic core | Hermes / AI | User |
|---|---:|---:|---:|
| Read sanitized market/research evidence | yes | yes | yes |
| Choose a candidate opportunity or genome | validate | yes | view |
| Calculate final permitted size/leverage | yes | propose only | set ceilings |
| Place/cancel/close an exchange order | yes | no | emergency controls |
| Set TP/SL and manage exits | validate/execute | propose | set ceilings only |
| Change Paper/Live, product, or pair scope | enforce | no | yes |
| Change risk ceilings | enforce | no | yes |
| Promote/rollback qualified strategies | deterministic gate | initiate proposal | view; no routine approval |
| Access Binance/provider/Telegram secrets | sealed adapters only | no | configure securely |
| Withdraw or transfer funds | no | no | outside this app |

The deterministic core treats AI output as untrusted data. All output is schema-validated, bounded, versioned, and linked to the evidence/model/strategy versions that produced it.

## 5. One-time Settings and controls

### 5.1 Persistent autonomous profile

The user configures and saves one durable profile:

- Execution mode: `Paper` or `Live`.
- Strategy mode: `Legacy` or `Autonomous`.
- Autonomous profile: standard opportunity-driven or Micro-Trade.
- Product switches: Spot and/or USD-M Futures.
- Pair selector limited to currently supported, exchange-validated symbols.
- **Max Capital per Trade (%)**. For Spot this caps cash allocated; for Futures it caps isolated margin. The UI continuously shows the corresponding USDT value under the field.
- **Max Futures Leverage**. This appears only when Futures is enabled. Hermes may propose and the core may choose any leverage from `1x` through this ceiling.
- **Max Total Exposure (%)**, with its current USDT equivalent.
- **Rolling 24-Hour Loss Limit (%)**, with its current USDT equivalent.
- Telegram destination status and per-category notification toggles.

The same percentage risk ceilings apply to Paper and Live so Paper qualification models the intended Live envelope. Paper uses its configured virtual equity; Live equivalents use reconciled Binance equity.

The engine chooses actual capital and leverage below the ceilings per opportunity. It must not treat a ceiling as a default allocation.

### 5.2 Start, pause, scope changes, and emergencies

- **Start Autonomous Trading** runs preflight and starts only if all required gates pass.
- Turning a pair or product off blocks new entries for that scope. Existing positions remain protected and are managed to a safe strategy-defined exit.
- **Pause Trading** blocks all new entries while continuing protection and position management.
- **Cancel All** cancels eligible open entry orders after confirmation and 2FA; it does not remove required protective orders from open positions.
- **Close All** cancels entries and reduces/closes application-managed positions using the safest available exchange path after confirmation and 2FA.
- Critical circuit-breaker and unresolved-reconciliation states cannot be cleared by repeatedly pressing Start.

### 5.3 Live arming

Live is an application-controlled persisted state, not an environment-mode shortcut. Initial arming requires:

1. authenticated admin session;
2. TOTP 2FA;
3. a clear confirmation summary showing products, pairs, equity, percentage/USDT ceilings, and Futures leverage ceiling;
4. valid server-side Binance credentials with read and required Spot/Futures trading permissions only;
5. withdrawals and transfers disabled on the API key;
6. mandatory Paper qualification;
7. healthy OpenCodex/Hermes routes, market data, database, Telegram critical-alert path, and Binance reconciliation.

The armed state survives a normal restart. Trading does not resume blindly: startup enters reconciliation-only mode and enables new entries only after the recovery protocol passes.

Routine autonomous strategy promotions do not require repeated user approval. When Live is already armed, a newly qualified strategy enters the smallest permitted Live canary and scales only through deterministic gates.

## 6. Trading lifecycle

### 6.1 Continuous observation

For every selected pair, the core maintains:

- exchange symbol filters and current trading status;
- WebSocket quotes/order updates with REST recovery;
- tick/order-book context where available;
- closed candles and features across strategy-requested bounded timeframes;
- data freshness, gap, duplicate, and forming-candle checks;
- cached research/economic/news evidence with provenance and expiry;
- current account-wide exposure, P&L, fees, funding, and risk state.

Market ingestion, protective monitoring, research, and Hermes learning are separate workers. Slow news search or model inference cannot block order reconciliation or protection.

### 6.2 Opportunity and entry

1. A deterministic scheduler/event detector identifies that an enabled pair is eligible for evaluation.
2. Active qualified strategies and Hermes-provided contextual reasoning produce a typed opportunity proposal.
3. The evidence layer reports freshness, reliability, relevance, conflicts, and missing sources.
4. The deterministic risk engine calculates the maximum permitted allocation and Futures leverage using equity, volatility, liquidity, correlation, current exposure, loss state, exchange filters, and user ceilings.
5. The proposal is rejected or clamped if any bound is violated.
6. The broker submits an idempotent Paper or Live order and persists intent before side effects.
7. Fill events, including partial fills, update the ledger and protection quantities.

No entry is allowed when Binance state is uncertain, required market data is stale, protection cannot be installed, the rolling-loss breaker is active, or minimum evidence quality is unmet.

### 6.3 Position management and exit

- Spot positions are unleveraged holdings purchased with available quote balance.
- Futures positions are isolated-margin long or short positions. The engine accounts for maintenance margin and liquidation distance, but protection must be substantially inside liquidation.
- Hermes can propose TP, SL, trailing, invalidation, and duration behaviour; deterministic strategy/risk contracts validate and execute it.
- Exchange-native reduce-only protection is installed immediately where Binance supports it.
- Protection and emergency exits never wait for Hermes, OpenCodex, web search, or the dashboard.
- The engine tracks entry, average fill, mark, margin, leverage, liquidation estimate, protection, holding time, gross/net P&L, fees, funding, and slippage.
- On close, the complete cost-adjusted outcome becomes a reflection event.

## 7. Risk system

### 7.1 Per-trade and account-wide controls

Risk evaluation is account-wide across enabled Spot and Futures products and all concurrent selected pairs.

- `Max Capital per Trade` caps Spot cash or Futures isolated margin for one position.
- `Max Futures Leverage` is a ceiling; selected leverage may be lower.
- `Max Total Exposure` caps aggregate risk-adjusted notional exposure.
- Correlated positions consume a shared concentration budget rather than appearing independent.
- Available balance is eligible capital, but the engine never assumes the full balance should be deployed.
- Risk reporting consolidates relevant Spot and Futures equity into a USDT equivalent, while execution uses funds already available in the required Binance wallet. GoldGuard does not transfer funds between wallets.
- Exchange minimum sizes that cannot fit inside the risk envelope cause `HOLD`, not rounding upward beyond the ceiling.

### 7.2 Rolling 24-hour loss circuit breaker

The combined account-wide rolling loss calculation includes:

- realized trading P&L;
- unrealized P&L on application-managed positions;
- commissions and other exchange fees;
- Futures funding;
- measured slippage.

When the configured limit is reached:

1. block and cancel new entries;
2. preserve or install protection;
3. safely reduce/close application-managed positions according to the breaker protocol;
4. persist the breaker and evidence;
5. send a mandatory Telegram critical alert when Telegram is enabled.

The breaker may automatically clear only after losses age out of the rolling window and reconciliation, data, protection, and system-health gates all pass. Security, credential, or unrecoverable reconciliation failures require user action.

### 7.3 No forced trading

Risk and evidence vetoes outrank opportunity frequency. No daily profit target, trade count, or model instruction can override a `HOLD`, breaker, stale-data condition, or risk ceiling.

## 8. Research and evidence

### 8.1 Source roles

- Binance is authoritative for tradable symbols, market data used for execution, account state, orders, and fills.
- Forex Factory is an important calendar/news input. Forum posts are untrusted commentary and cannot independently authorize a trade.
- Official central-bank, government-statistics, regulator, issuer, and exchange announcements are preferred primary evidence.
- Reputable financial reporting and bounded web search provide additional context and discovery.

### 8.2 Evidence contract

Every normalized evidence item stores source, URL or stable identifier, publication/event time, retrieval time, affected assets, event class, reliability, freshness, relevance, and extracted claims. Evidence is cached in the background and expires by source/event type.

- One source outage uses qualified fallbacks and degrades confidence visibly.
- Conflicting or weak evidence reduces permitted size or produces `HOLD`.
- Search content is treated as untrusted input and cannot issue tools, change Settings, or create orders.
- An evidence outage must not prevent deterministic management of existing positions.
- Fabricated sources, timestamps, health, sentiment, or profitability values are prohibited.

## 9. Hermes learning and strategy lifecycle

### 9.1 Learning records

Every closed trade and material rejected decision creates an immutable learning record containing:

- Paper/Live mode, product, pair, strategy/genome hash, and model/route version;
- market regime and multi-timeframe feature snapshot;
- evidence available at decision time;
- intended versus actual entry, size, leverage, TP/SL, and exit;
- realized/unrealized path, gross/net P&L, fees, funding, and measured slippage;
- order/partial-fill/protection/reconciliation events;
- rule compliance and data/system health;
- outcome attribution and confidence.

Hermes classifies outcomes into bounded categories such as invalid hypothesis, timing, regime mismatch, weak evidence, over-sizing proposal, execution quality, protection failure, data/system failure, or normal variance. A losing trade is not automatically a mistake, and a winning trade is not automatically a good decision.

Paper and Live experiences share reusable lessons only through explicit tags. Live execution lessons cannot silently contaminate Paper equity, and Paper fills cannot be represented as Live evidence.

### 9.2 Candidate generation

Hermes authors declarative strategy genomes using allowlisted indicators, conditions, exits, timeframes, and bounded parameters. It may mutate a small number of parameters or propose a new bounded hypothesis. The core rejects arbitrary code, unknown operators, excessive complexity, risk-bound changes, or unsupported data dependencies.

Each candidate has a parent, hypothesis, evidence references, canonical representation, deterministic hash, authoring model/version, and immutable evaluation history.

### 9.3 Qualification pipeline

Candidates move only through:

`candidate -> development backtest -> purged walk-forward validation -> sealed holdout -> Paper shadow -> qualified -> tiny Live canary -> scaled active`

The following deterministic release-policy floors are not user-reducible from the application. First-Live qualification requires:

- at least 200 closed Paper trades;
- at least 14 elapsed calendar days;
- evidence from at least two detected market regimes;
- positive net expectancy after fees, spread, slippage, and funding;
- a greater-than-zero lower bound on a 95% bootstrap confidence interval for net expectancy;
- maximum drawdown inside the user's rolling-loss envelope;
- no unresolved protection, reconciliation, stale-data, security, or ledger-integrity incident;
- successful restart and fault-injection qualification.

For a newly learned strategy after the account is already qualified, the strategy must pass historical gates plus at least 100 closed shadow trades over at least seven elapsed days and at least two regimes before Live-canary eligibility. These are minimums; the deterministic gate may require more evidence when uncertainty is high.

Hermes cannot view the sealed holdout before the deterministic freeze/evaluation step and cannot alter the thresholds.

### 9.4 Automatic promotion, rollback, and quarantine

- Passing a gate advances the candidate automatically; failure records structured reasons.
- When Live is not armed, qualified strategies remain Paper/shadow only.
- When Live is armed, a qualified strategy begins at the smallest risk-valid canary allocation.
- Scaling occurs in bounded steps only after fresh cost-adjusted evidence.
- Drawdown, execution anomalies, protection failures, regime drift, data degradation, or material underperformance automatically stop scaling and trigger rollback/quarantine.
- Rollback is a background safety worker, never dependent on a dashboard/API read.
- The last known-safe strategy is restored byte-identically when allowed; otherwise new entries remain stopped.
- Promotion churn limits prevent rapid strategy thrashing.
- All transitions and reports are durable and visible in the Learning dashboard.

Hermes may learn continuously, but it cannot rewrite application code, expand its tool surface, change risk ceilings, enable Live/pairs/products, access secrets, or override gates.

## 10. Reliability and recovery

### 10.1 Order correctness

- Every order intent has a unique deterministic client-order identifier and idempotency key.
- After a timeout or uncertain response, the broker queries Binance before retrying.
- Duplicate WebSocket/REST events are de-duplicated transactionally.
- Partial fills create matched protection for the filled quantity and preserve remaining-order state.
- Unsupported precision, minimum notional, insufficient balance/margin, or rejected leverage produce explicit terminal/recoverable states.
- A per-pair execution lock and durable state transitions prevent concurrent duplicate entries.
- Event-stream reconciliation is supplemented by periodic authoritative REST snapshots while Live is armed.
- A Live account should be dedicated to GoldGuard. Unknown manual/external orders or positions block new entries in the affected scope and trigger an alert; GoldGuard does not adopt, cancel, or close them without explicit ownership evidence.

### 10.2 Data and dependency failure

- A stale-data watchdog runs independently of quote arrival.
- WebSocket loss triggers bounded reconnect and REST reconciliation.
- Clock drift, exchange rate limits, maintenance, symbol changes, and market suspension become explicit health states.
- OpenCodex or Hermes outage blocks new AI-dependent entries while existing positions remain deterministically protected and managed.
- Research-source outage uses fallbacks; Binance account/order uncertainty always blocks entries.
- The system never converts unavailable data into zero, healthy, current, or profitable-looking values.

### 10.3 Restart reconciliation

Startup follows this fixed sequence:

1. acquire the single active runtime lease;
2. open the ledger and pass schema/integrity checks;
3. start in `RECONCILING` with all new entries blocked;
4. fetch Binance server time, exchange information, balances, positions, open orders, and recent fills;
5. match exchange state to durable intents using client-order IDs;
6. import externally completed application orders and flag unknown manual/external activity;
7. verify or repair TP/SL/reduce-only protection without increasing risk;
8. recalculate exposure, rolling loss, and qualification state;
9. prove market/provider/Hermes/Telegram readiness required by the current mode;
10. resume the persisted armed state only when every mandatory check passes.

Any unresolved mismatch leaves new entries blocked and generates a critical diagnostic and Telegram alert. The engine does not guess whether an order filled.

### 10.4 Durability and backups

Settings, credentials-status metadata, decisions, intents, orders, fills, positions, account snapshots, P&L, evidence, reflections, lessons, genomes, evaluations, promotions, breakers, notifications, and audit events are durable.

The production ledger uses a Railway persistent volume, transactional migrations, WAL/foreign keys where SQLite remains in use, periodic integrity checks, encrypted off-service backups, retention, and a tested restore procedure. OpenCodex provider auth and Hermes memory use separate persistent volumes and backup policies.

## 11. Security

- Single-admin authentication uses a strong password hash, secure HttpOnly session cookie, CSRF protection, throttling, idle/absolute expiry, and TOTP 2FA.
- Live arming, risk-ceiling increases, credential changes, Cancel All, and Close All require recent authentication and 2FA.
- Binance API keys permit only required reads and Spot/Futures trading. Withdrawal and transfer permissions must be disabled.
- Binance, OpenCodex provider, Hermes bridge, Telegram, session, and backup secrets remain server-side and are redacted from representations, exceptions, responses, logs, prompts, exports, and notifications.
- The browser shows only `configured`, `missing`, `invalid`, `quota-limited`, or equivalent credential status.
- Service-to-service tokens are distinct, rotatable, and scoped. OpenCodex management authority is not given to Hermes.
- CORS is restrictive; mutating APIs require authentication, CSRF, validation, audit events, and rate limits.
- Prompt injection and malformed AI output are treated as untrusted input; neither can invoke a broker or mutate configuration.
- Every sensitive action records actor, time, prior/new non-secret state, request correlation, and outcome.

## 12. Dashboard and user experience

The interface is responsive and uses familiar Binance trading language while remaining explicitly autonomous.

### 12.1 Main surfaces

- **Overview:** Paper/Live status, running/paused/reconciling/breaker state, equity, exposure, rolling P&L, current positions, AI activity, and critical health.
- **Markets:** enabled pair selector, multi-timeframe charts, book/price state, regime, research/news evidence, and freshness.
- **Open Orders:** product, pair, side, type, quantity, filled/remaining, price, protection relationship, age, and state.
- **Positions / Spot Holdings:** entry/average/mark, isolated margin, leverage, liquidation estimate, TP/SL, gross/net P&L, fees, funding, slippage, and duration.
- **Trade History:** complete order/fill lifecycle, net outcome, strategy, reason, and linked postmortem.
- **Research:** sourced evidence, calendar events, freshness, agreement/conflict, and AI summary.
- **Strategies / Learning:** active and shadow genomes, family tree, hypotheses, evaluations, Paper/Live evidence, promotions, canaries, rollbacks, quarantine, and lessons.
- **Diagnostics:** Binance, market streams, database, OpenCodex, Antigravity route, Hermes, Telegram, backups, reconciliation, last successful cycle, and explicit blockers.
- **Settings:** the persisted autonomous profile, security, provider route selection/status, notification preferences, and emergency controls.

### 12.2 Truthfulness rules

- Every number comes from a named backend record or displays unavailable/stale.
- Paper and Live are unmistakably labelled on every relevant screen and record.
- Timestamps include timezone and age.
- No seeded/mock order, position, profit, activity, news, quota, health, or learning data appears in production UI.
- Empty, loading, degraded, stale, and error states are distinct.
- AI explanations include reason codes and cited evidence but never conceal deterministic vetoes.

## 13. Telegram notifications

Telegram is the initial notification channel because bot delivery is simple and has no required paid workspace plan. The bot token is configured securely outside chat and never returned by the API.

Settings control:

- trade opened;
- trade closed and net result;
- TP/SL or protection changes;
- daily concise report;
- learning, promotion, rollback, and quarantine;
- important news/economic events;
- health, restart, and recovery;
- reconciliation issues;
- circuit breakers and security events.

When Telegram is enabled, the following cannot be muted: circuit-breaker activation, missing/failed position protection, Binance account/order mismatch, security event, unrecoverable reconciliation, and safety shutdown. A **Test Notification** action verifies the selected destination. Messages contain no secret or sensitive credential data.

The daily report summarizes equity/P&L with Paper/Live label, gross and net results, fees/funding/slippage, positions/trades, drawdown and risk use, important holds, strategy/learning changes, degraded time, and outstanding action items.

## 14. Verification and acceptance

### 14.1 Baseline and automated verification

Before new functionality is credited, current test, lint, type, startup, and UI failures are recorded. Completion requires fresh evidence from:

- backend unit, property, contract, integration, security, and end-to-end suites;
- Ruff and strict type checking;
- frontend unit tests, type checking, production build, and lint where configured;
- Playwright desktop and mobile journeys across every tab and control;
- Docker Compose configuration, image builds, health checks, and persistent-volume restarts.

Tests cover Spot/Futures sizing, isolated leverage, liquidation distance, TP/SL, order precision, partial fills, fees, funding, slippage, concurrent exposure, circuit breakers, qualification, promotion, rollback, and security boundaries.

### 14.2 Fault injection

The local system must survive or safely stop during:

- process/container/Railway-style restart;
- WebSocket disconnect, delayed REST, timeout after submit, duplicate messages, and rate limiting;
- stale/gapped/duplicate market data and exchange clock drift;
- partial fill, rejected order, failed cancel, and failed protection installation;
- Hermes, OpenCodex, Antigravity provider, Telegram, and individual news-source outages;
- database migration/integrity failure and backup restore;
- malformed or prompt-injected evidence and invalid model output.

The acceptance assertion is not merely “an error was logged.” It must prove the correct state, order/protection result, entry block, persisted audit record, truthful UI status, and required notification.

### 14.3 Local diagnostics

The actual isolated GoldGuard, Hermes, and OpenCodex services must run together. Diagnostics must prove:

- real public Binance market data and symbol filters;
- Paper Spot and Futures lifecycle through close and reflection;
- Hermes invoking the configured Antigravity model through OpenCodex;
- persisted settings, ledger, model route, provider auth, and Hermes memory after restart;
- strategy candidate submission, evaluation, shadowing, promotion, and rollback;
- truthful orders, positions, P&L, research, learning, and diagnostics UI;
- Telegram test and critical notification routing.

Automated diagnostics do not place Live orders.

### 14.4 Live canary authorization

No real order is placed during development or diagnostics without the user's explicit Live arming in the completed app. After all qualification and safety gates pass, the smallest valid canary is user-authorized through that arming flow. Abnormal execution, data, protection, or P&L behaviour triggers automatic rollback/closure according to the risk protocol.

### 14.5 Definition of ready

“Ready for user push and Railway deployment” requires:

- no unresolved critical/high defects in the approved scope;
- all verification commands passing with recorded output;
- actual local service and restart evidence;
- no secret leakage;
- Paper qualification and qualification-report visibility;
- working Binance reconciliation and exchange-side protection logic;
- working Telegram critical alerts;
- deployment manifests, persistent-volume map, backup/restore instructions, and runbooks;
- a candid list of any remaining non-blocking limitations.

Functional readiness is not a profitability guarantee. A strategy that does not pass qualification remains Paper-only while Hermes continues learning.

## 15. Delivery workstreams

Implementation will be decomposed into gated plans while preserving one Git branch:

1. **Isolation and baseline:** verify the isolated clone, runtime ownership, current failures, and data/service boundaries.
2. **Core contracts and persistent Settings:** product/pair profile, risk ceilings, state, authentication, 2FA, and audit ledger.
3. **Trading and risk engine:** multi-pair Paper Spot/Futures, sizing, leverage, exits, account exposure, costs, and breakers.
4. **Hermes and OpenCodex:** real Hermes service ownership, Antigravity routing, postmortems, memory, candidate lifecycle, promotion, rollback, and quarantine.
5. **Research and intelligence:** multi-timeframe data, order-book context, primary/news/calendar evidence, scoring, cache, and degraded behaviour.
6. **Live Binance execution:** Spot/Futures broker adapters, idempotency, partial fills, exchange-native protection, reconciliation, and restart recovery.
7. **Dashboard and Telegram:** truthful Binance-like surfaces, persisted Settings, diagnostics, notifications, and emergency controls.
8. **Qualification and release:** complete automated/fault/browser/runtime evidence, Paper qualification, user-authorized smallest Live canary, and Railway handoff.

Each workstream has tests and running acceptance evidence. A later workstream cannot retroactively turn an unverified earlier dependency into “complete.”

## 16. Explicit non-goals and limitations

- No guaranteed returns, guaranteed win rate, guaranteed daily profit, or guaranteed 1,000 trades.
- No Binance Options contracts in this release.
- No leveraged Spot, Spot borrowing, or cross-margin Futures.
- No direct stock, forex, non-Binance commodity, or other-exchange execution in this release.
- No fund withdrawal, transfer, deposit management, or custody automation.
- No AI-authored executable code or autonomous modification/deployment of the application.
- No AI override of user risk ceilings, qualification, evidence, reconciliation, or security gates.
- No claim of 24/7 availability from an application process alone; availability depends on Railway, Binance, providers, network, and durable recovery. During dependency failure, safe degraded behaviour is the requirement.

## 17. User intervention after setup

After credentials are securely configured, the profile is saved, mandatory Paper qualification succeeds, and autonomous trading is started, routine operation is autonomous across normal restarts.

The user returns only to:

- change Settings, enabled products/pairs, or risk ceilings;
- pause/stop trading or invoke emergency controls;
- repair revoked/expired credentials or provider authentication;
- address a Binance account/product change, security event, or unrecoverable reconciliation;
- review reports and performance by choice.

Routine entries, exits, TP/SL, allocation, Futures leverage, research, learning, strategy promotion, rollback, and daily reporting require no repeated user intervention.
