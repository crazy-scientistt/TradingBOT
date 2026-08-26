# Autonomous Paper-First GoldGuard Design

## Goal

Make GoldGuard an honest, autonomous paper-trading product for a non-trader: one clear start action, real market data, deterministic execution and risk controls, automatic bounded strategy improvement, automatic rollback, and a low-noise live activity feed.

## Product decisions

- The default execution mode is paper trading with the configured virtual balance. The UI must never imply that a paper position is live.
- Real-money execution remains disabled by the server capability gate and is not exposed as a casual mode toggle.
- Routine strategy candidates are promoted automatically after objective gates. Human approval is required only for account credentials, live capability, risk-envelope changes, or manual circuit-breaker reset.
- The bot may not change capital limits, widen stops, bypass data-quality gates, execute code from an LLM, or promote a candidate that has not passed the configured evidence gates.
- When a source or subsystem is unavailable, the UI reports unavailable/stale/degraded state rather than rendering demo values.

## Runtime architecture

`TradingRuntime` owns the live paper session and is initialized by the FastAPI lifespan. It composes the Binance public market client, verified candle store, paper broker, `TradingCoordinator`, `GenomeRuntime`, `RiskEngine`, context engine, optional AI veto, memory bank, and a persistent state machine.

The runtime has two paths:

1. A market-data path receives book-ticker updates and calls `TradingCoordinator.monitor_open_position` immediately for stop/target protection.
2. A closed-candle path evaluates each new 15-minute candle exactly once, builds a feature snapshot, runs deterministic strategy, professional context checks, asynchronous AI veto, risk sizing, paper fill, ledger persistence, and reflection creation.

The real coordinator dependencies use explicit async adapters and typed request objects. No test-only mock interface is used by production startup.

## Autonomous improvement

Hermes runs on a bounded schedule while the bot is operating or when manually triggered. Each candidate:

- must be a valid immutable genome with one or two bounded declarative mutations;
- must preserve the risk envelope and execution mode;
- must pass development, validation, sealed holdout, and baseline-relative performance gates;
- must complete the configured paper/shadow evidence window without risk violations;
- enters a limited canary stage before becoming active;
- is automatically rolled back when drawdown, data quality, execution error, or performance-drift thresholds are exceeded.

Actual closed trades produce reflections. Rule violations are stored separately from strategy lessons and cannot be used to justify a strategy promotion. The LLM proposes hypotheses and explains decisions; deterministic code validates and applies them.

## Data

The system bootstraps verified PAXGUSDT 15-minute and 1-hour history from official Binance market-data endpoints or archives, stores checksums/manifests, rejects gaps/duplicates/forming candles, and exposes bootstrap progress. Three years of data is a research dataset, not a guarantee of future returns.

Macro context uses cited primary sources where available (FRED real yields, Federal Reserve calendar/statements, BLS releases, and Paxos attestations). Context can veto or reduce confidence; it cannot create an order without a deterministic setup.

## Observability

Every decision emits a structured `AgentEvent` with timestamp, action (`HOLD`, `BUY`, `SELL`, `STOP`, `TARGET`, `ERROR`), plain-language reason, reason codes, feature summary, data freshness, strategy id/hash, risk result, and optional lesson reference. Durable decision/trade records remain in SQLite. The display stream is bounded to the newest 30 events and expires routine events after a short TTL; it is not an unbounded log.

The API provides one initial dashboard snapshot and a Server-Sent Events stream for incremental updates. The frontend reconnects with backoff and shows a degraded state when disconnected.

## Beginner experience

The default screen uses plain language: `Start paper trading`, `Pause new entries`, `Emergency stop`, `Why the bot is holding`, and `What the bot learned`. Advanced tabs remain available but are clearly marked.

Starting performs a preflight check for database integrity, market data, verified history, strategy, risk preset, and required provider routes. The action is rejected with a human-readable checklist when any gate fails.

Pause stops new entries but continues protective monitoring for an open paper position. Emergency stop closes paper positions, halts all mutation paths, persists the halted state, and cannot be cleared by pressing Start.

## Error and safety behavior

- API mutations require a server-side authorization boundary in production and restrictive CORS.
- State, paper account balance, fills, decisions, and halted status survive process restart.
- All external calls have timeouts, bounded retries, rate-limit backoff, and explicit degraded status.
- No endpoint returns fabricated profitability metrics or provider health.
- Frontend has an error boundary and typed loading/error/empty states.

## Verification targets

- Unit tests cover event retention, preflight, autonomous promotion/rollback, async coordinator adapters, and truthful empty/error API responses.
- Integration tests prove one closed candle creates one decision chain, a valid signal can create a paper fill, and a closed trade creates a reflection.
- Browser tests visit every tab at desktop and mobile widths, start/pause/stop paper trading, display live events, and confirm no console errors.
- A deployment check verifies the actual Docker build context and starts the backend with a persisted data volume.
