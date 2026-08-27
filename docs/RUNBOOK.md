# GoldGuard Production Runbook

## 1. System Architecture & Component Mapping

| Component | Port / Interface | Primary Responsibility | Fail-Mode Policy |
| :--- | :--- | :--- | :--- |
| **OpenCodex Proxy Gateway** | `:10100` | Multi-provider hub routing to `google-antigravity/gemini-3.7-flash` | Degraded / Fallback |
| **GoldGuard Core Engine** | `:8000` | SQLite Ledger, RiskEngine, GenomeRuntime, TradingCoordinator | Fail-Closed on Entry, Fail-Open on Position Protection |
| **Hermes Strategy Loop** | Background Task | Autonomous hypothesis testing, backtesting, walk-forward gating | Strict daily budget (10 iter, 50 backtests, 20 web calls) |
| **Frontend Cockpit & Studio** | `:5173` | Rich dashboard, visual genome builder, route matrix, emergency halts | Real-time SSE / REST |

---

## 2. Emergency Incident Response Procedures

### 2.1 Triggering Emergency Kill Switch
If unexpected market volatility, exchange anomaly, or critical divergence occurs:
1. **Via Dashboard**: Navigate to `Cockpit` tab -> click `Trigger Kill Switch` -> confirm dialog.
2. **Via Backend CLI**:
   ```bash
   python scripts/run_shadow_trading.py --db data/goldguard.db --kill-now
   ```
3. **Behavior**:
   - Immediately cancels all pending limit/stop orders.
   - Market liquidates all open long positions in PAXG/USDT.
   - Transitions state to `EMERGENCY_STOPPED`.
   - Prevents any new order submission until manual clearance.

### 2.2 Revoking Autonomy / Human Approval Mode
If Hermes produces unexpected proposals or market regime requires human oversight:
1. Click `Revoke Autonomy` on the Emergency Cockpit.
2. Hermes strategy loop is paused from promoting candidates automatically into `shadow` or `active`.
3. All new candidate genomes require manual review in `Strategy Studio`.

### 2.3 Reverting to Safe Baseline Genome
To revert active strategy back to vetted `trend-pullback-v1`:
```bash
python -c "from goldguard.storage.database import Database; from goldguard.storage.repositories import GenomeRepository; db = Database('data/goldguard.db'); r = GenomeRepository(db); r.update_status('trend-pullback-v1', 'active')"
```

---

## 3. Quota Management & Circuit Breakers

- **Backtest Quota**: Maximum 50 evaluations per rolling 24 hours.
- **Web Search Quota**: Maximum 20 searches per rolling 24 hours.
- **Consecutive Gate Failure Circuit Breaker**: If 3 consecutive candidate genomes fail validation or holdout gates, `HermesResearchLoop` automatically suspends itself and transitions to `AUTONOMY_SUSPENDED`.

---

## 4. Disaster Recovery & Database Restoration

The single source of truth is SQLite WAL-mode database at `data/goldguard.db`.
- **Integrity Check**:
  ```bash
  python scripts/health_check.py --db data/goldguard.db --gateway-url http://localhost:10100
  ```
- **Live Backup**:
  ```bash
  sqlite3 data/goldguard.db ".backup 'data/backup_goldguard_$(date +%Y%m%d_%H%M%S).db'"
  ```

## 5. Verified Market-Dataset Bootstrap

Historical candles are downloaded from Binance's public market-data API. The
bootstrap is resumable: each page is checkpointed under
`data/market/<SYMBOL>/` and the manifest is marked `VERIFIED` only after both
requested timeframes are closed, contiguous, unique, and checksum-matched.
Unverified data must not be used to warm a runtime or run a backtest.

From the repository root (with the backend environment active):

```bash
python scripts/bootstrap_history.py \
  --symbol PAXGUSDT \
  --storage-dir data \
  --warmup-days 30 \
  --timeframes 15m,1h
```

The default range is the previous three years ending at the current UTC hour.
For a deterministic run, provide explicit UTC boundaries, for example:

```bash
python scripts/bootstrap_history.py \
  --start 2023-01-01T00:00:00+00:00 \
  --end 2026-01-01T00:00:00+00:00
```

The command prints page-level progress and exits non-zero unless the final
status is `VERIFIED`. Inspect `data/market/PAXGUSDT/manifest.json` and
`progress.json`; a `CORRUPT` or `DOWNLOADING` status is a hard data gate, not a
signal to run a backtest with partial candles. A later invocation resumes from
the checkpoint after transient API failures.
