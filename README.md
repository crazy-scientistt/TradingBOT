# GoldGuard: Autonomous Institutional-Grade Gold Trading System

[![Backend Test Suite](https://img.shields.io/badge/backend%20tests-207%20passed-brightgreen.svg)]()
[![Frontend Tests](https://img.shields.io/badge/frontend%20tests-8%20passed-brightgreen.svg)]()
[![Type Safety](https://img.shields.io/badge/types-mypy%20%7C%20tsc%20clean-blue.svg)]()
[![Code Style](https://img.shields.io/badge/linter-ruff%20clean-blue.svg)]()

GoldGuard is an autonomous quantitative algorithmic trading engine designed for PAXG/USDT (Tokenized Physical Gold on Binance Spot). It blends deterministic state machines, pure AST strategy genomes, real-time macro context ingestion, multi-provider LLM veto gating via OpenCodex Proxy (`google-antigravity/gemini-3.7-flash` high effort reasoning), and an isolated autonomous strategy research loop (Hermes).

**Local development is paper-only.** On your PC:

```bash
sh scripts/bootstrap_local_env.sh   # once
sh scripts/start_local.sh
python scripts/verify_local_stack.py
```

Open http://localhost:8000 (GoldGuard), http://localhost:10100 (OpenCodex — add Antigravity/Gemini). Live stays disarmed. Full steps: [docs/operations/local-opencodex.md](docs/operations/local-opencodex.md).

---

## 🏛 System Architecture

```
                    ┌─────────────────────────────────────────────────────────┐
                    │               GoldGuard UI / Studio / Cockpit           │
                    │               (React 19 + TypeScript + Vitest)          │
                    └──────────────────────────┬──────────────────────────────┘
                                               │ HTTP / REST & SSE
                                               ▼
┌─────────────────────────────────────────────────────────────────────────────────────────────┐
│                                   GoldGuard Core Engine                                     │
│                                                                                             │
│  ┌──────────────────────────┐   ┌──────────────────────────┐   ┌─────────────────────────┐  │
│  │   TradingCoordinator    │──▶│    GenomeRuntime (Pure)  │──▶│  ProfessionalChecklist  │  │
│  │  (Idempotent Bar Scan)   │   │  (Safe AST Evaluation)   │   │  (Context Conflict Veto)│  │
│  └────────────┬─────────────┘   └──────────────────────────┘   └────────────┬────────────┘  │
│               │                                                             │               │
│               ▼                                                             ▼               │
│  ┌──────────────────────────┐   ┌──────────────────────────┐   ┌─────────────────────────┐  │
│  │     Paper/Live Broker    │◀──│   Deterministic Risk     │◀──│   AI Decision Veto      │  │
│  │   (Instant Bracket Stop) │   │ (24h Rolling Loss Caps)  │   │  (OpenCodex Gemini 3.7) │  │
│  └────────────┬─────────────┘   └──────────────────────────┘   └────────────┬────────────┘  │
│               │                                                             │               │
│               ▼                                                             ▼               │
│  ┌───────────────────────────────────────────────────────────────────────────────────────┐  │
│  │                  SQLite Write-Ahead-Log (WAL) Durable Ledger Repository               │  │
│  └───────────────────────────────────────────┬───────────────────────────────────────────┘  │
│                                              │                                              │
│                                              ▼                                              │
│  ┌───────────────────────────────────────────────────────────────────────────────────────┐  │
│  │                      Hermes Autonomous Strategy Research Loop                         │  │
│  │  ┌──────────────────┐   ┌──────────────────┐   ┌─────────────────┐   ┌─────────────┐  │  │
│  │  │ StrategyProposal │──▶│ BacktestEngine   │──▶│ WalkForwardGate │──▶│ Sealed      │  │  │
│  │  │  (Bounded LLM)   │   │ (Friction Model) │   │ (WFE, DSR, PBO) │   │ Holdout 15% │  │  │
│  │  └──────────────────┘   └──────────────────┘   └─────────────────┘   └─────────────┘  │  │
│  └───────────────────────────────────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────────────────────────────────┘
                                               │
                                               ▼
                    ┌─────────────────────────────────────────────────────────┐
                    │               OpenCodex Gateway Proxy (:10100)          │
                    │               (Gemini 3.7 Flash High Reasoning)         │
                    └─────────────────────────────────────────────────────────┘
```

---

## ⚡ Key Features

1. **Deterministic Strategy Genome DSL**: Strategies defined as immutable, JSON-serializable AST structures with deterministic SHA-256 hash identity and hard boundary limits.
2. **Zero-Latency Fail-Open Position Protection**: Stop Loss and Take Profit brackets are monitored directly on incoming ticks without AI or network latency.
3. **Fail-Closed Decision Gating**: AI Trade Veto engine requires explicit schema-validated `APPROVE_ENTRY` with high confidence; any error, timeout, or unknown reason code automatically fails closed.
4. **Hermes Strategy Loop**: Autonomous background loop with daily quotas (50 backtests, 20 web searches) and consecutive-failure circuit breakers.
5. **Multi-Gate Walk-Forward Validation**: 70/15/15 chronological partition with strictly sealed, one-shot holdout validation and permanent quarantine on overfitting.
6. **Dual-Namespace Memory Bank**: Forward trade post-mortems and historical reflections categorized by fine-grained lesson codes (`CHOP_WHIPSAW`, `STOP_HIT_EXPANSION`, `TP_CLEAN`, etc.).
7. **Emergency Cockpit & Strategy Studio**: Instant kill switch, autonomy revocation, baseline strategy rollback, real-time genome diffing, and interactive condition builder.

---

## 🚀 Quick Start

### Run OpenCodex + Hermes + GoldGuard on your PC

Docker Desktop required. Live stays disarmed.

```powershell
powershell -ExecutionPolicy Bypass -File scripts/bootstrap_local_env.ps1
powershell -ExecutionPolicy Bypass -File scripts/start_local.ps1
python scripts/verify_local_stack.py
```

macOS / Linux:

```bash
sh scripts/bootstrap_local_env.sh
sh scripts/start_local.sh
python scripts/verify_local_stack.py
```

Then open http://localhost:8000 (GoldGuard) and http://localhost:10100 (OpenCodex dashboard — add Gemini there). Details: [local OpenCodex](docs/operations/local-opencodex.md).

### 1. Run Complete Test Matrix

```bash
# Run backend pytest suite
uv run pytest backend/tests -q

# Run frontend vitest suite
npm --prefix frontend test

# Run static typechecks & linters
uv run ruff check backend scripts
uv run mypy backend/goldguard
npm --prefix frontend run typecheck
```

### 2. Launch Shadow Trading Runner

```bash
python scripts/run_shadow_trading.py --db data/goldguard.db --symbol PAXGUSDT --cash 100.0 --autonomy
```

### 3. Bootstrap Verified Market History

Backtests and runtime warmup require a verified, closed-candle dataset. From
the repository root, run the resumable three-year bootstrap (15-minute and
1-hour candles plus 30 days of warmup):

```bash
python scripts/bootstrap_history.py --symbol PAXGUSDT --storage-dir data --warmup-days 30 --timeframes 15m,1h
```

The command prints page progress and exits non-zero unless
`data/market/PAXGUSDT/manifest.json` reaches `VERIFIED`. `DOWNLOADING` and
`CORRUPT` datasets are hard gates; do not use their partial candles for a
backtest or runtime startup. Supply `--start` and `--end` as UTC ISO-8601
timestamps when a reproducible range is needed.

### 4. Verify Production Health

```bash
python scripts/health_check.py --db data/goldguard.db --gateway-url http://localhost:10100
```

### 5. Local Docker (paper only)

```bash
docker compose -f docker-compose.local.yml --env-file .env.autonomous up --build
```

### 6. Single-Command Docker Deployment (legacy compose)

```bash
docker compose -f docker-compose.prod.yml up -d
```

---

## 📚 Documentation

- [Local OpenCodex on your PC](docs/operations/local-opencodex.md)
- [Operator handoff](docs/operations/operator-handoff.md)
- [Production Runbook](docs/RUNBOOK.md)
- [Autonomy & Strategy Specification](docs/AUTONOMY_SPEC.md)
- [Full Master Implementation Plan](docs/superpowers/plans/2026-08-26-hermes-autonomous-gold-trader.md)
