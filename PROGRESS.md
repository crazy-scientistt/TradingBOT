# TradingBOT Autonomous — Progress Report

> Generated: 2026-08-29
> Repo: https://github.com/crazy-scientistt/TradingBOT
> Honest status: Paper-first platform is wired and fail-closed. Live is **not** armed.
> Profitability is **not** claimed.
> Preview cockpit: GoldGuard paper desk is running in the Grok live preview.

---

## Completed in this session

### Live execution no longer invents fills
- `BinanceTransport` raises `TRANSPORT_CLIENT_REQUIRED` when no HTTP client is injected. It no longer returns a fake `{"status":"ok"}` payload.
- Timeouts become `BinanceTimeoutError`. Brokers query by `origClientOrderId` and **do not POST a second order**.
- `BinanceSpotBroker` / `BinanceFuturesBroker` parse exchange `status` / `orderId` / `executedQty`. Missing status is `MALFORMED_EXCHANGE_RESPONSE`, never `FILLED`.
- Quantities are stepped (`0.001234` → `0.0012` on spot). Snapshot reads account balances instead of hardcoding 10,000 USDT. `close()` fails closed until a reconciled owned position exists.
- `BinancePreflight` actually calls server time, account, and API restrictions. Credentials alone are not enough. Withdrawals/transfers enabled block readiness.

### Research / Hermes honesty
- Evidence adapters return **empty** without a client. Tests inject fixture clients. Production refresh no longer fabricates Fed/FF/Binance rows.
- Hermes tools no longer return a fake Sharpe 1.5 / 60% win rate. Unbound tools report `available: false` with a reason code. Holdout stays sealed.

### Reconciliation / images
- Missing exchange client is `EXCHANGE_UNAVAILABLE`, not ready.
- Backend image healthcheck is `/api/health/live`. Contract tests assert non-root USER, `$PORT`, `/data`, and OpenCodex `2.33.0`.

### Frontend
- `LoginPanel` test: password + TOTP, no session secret in web storage.

### Preview desk
- Forum HOLD no longer blocks the whole paper book. Authoritative ALLOW/HOLD owns the gate. Calendar REDUCE halves size.

---

## Phase status

| Phase | Name | Status |
|-------|------|--------|
| 1 | Control Plane & Security | Fail-closed live control tested |
| 2 | Paper Execution & Risk | Brokers, coordinator, supervisor loops wired |
| 3 | Research & Evidence | Adapters fail-closed without clients; no fabricated production evidence |
| 4 | Hermes Learning | Isolation + honest empty tools; live Hermes not running here |
| 5 | Live Binance Execution | Fake-transport brokers parse fills; **Live remains disarmed** |
| 6 | Dashboard & Telegram | Read-models + settings/login; bot not configured |
| 7 | Qualification & Reliability | Fail-closed qualification; not certified for live |
| 8 | Railway Release | Manifests written; **not deployed** |

---

## Remaining operator-owned

- Supply **Binance API keys** before any live arming path.
- Create a **Telegram bot** (token + chat ID).
- **Deploy to Railway** (private OpenCodex :10100, private Hermes :8642, public GoldGuard, volumes, secrets).
- Bind real evidence HTTP clients and a backtest runner; until then those surfaces stay empty/unavailable.
- Qualification stays fail-closed until paper evidence, backups, UI suite, and operator diagnostics exist.

## What this is not

- Live is **not** armed.
- The system is **not** profitable-by-default.
- Railway is **not** in production from this work.
- Empty orders/positions remain empty until the paper runtime actually trades.
