# Operator handoff

Code for all eight phases is in `main`. Live stays disarmed until you complete
the items below. The local OpenCodex path does **not** need Binance, Telegram,
or Railway.

## 0. Run it on your PC first (OpenCodex + Hermes + GoldGuard)

From the repo root, with Docker Desktop running:

```powershell
powershell -ExecutionPolicy Bypass -File scripts/bootstrap_local_env.ps1
powershell -ExecutionPolicy Bypass -File scripts/start_local.ps1
python scripts/verify_local_stack.py
```

macOS / Linux: `sh scripts/bootstrap_local_env.sh` then `sh scripts/start_local.sh`.

Then open:

- GoldGuard: http://localhost:8000
- OpenCodex dashboard: http://localhost:10100 — paste a Gemini / Antigravity key here
- Hermes health: http://localhost:8642/health

Full walkthrough: `docs/operations/local-opencodex.md`.

Paper trading runs without those keys. AI veto / Hermes research stay fail-closed
until OpenCodex lists a model.

## 1. Secrets (Railway or local `.env`, never chat)

- `GOLDGUARD_HERMES_BRIDGE_TOKEN`
- `OPENCODEX_API_AUTH_TOKEN` / `OPENCODEX_ADMIN_AUTH_TOKEN`
- Binance API key + secret (read + selected trade; withdrawals and transfers off)
- Telegram bot token + chat id
- Session / TOTP bootstrap password
- Backup passphrase

## 2. Deploy (you click deploy)

Three Railway services. GoldGuard is the only public domain.

| Service | Public | Volume |
|---------|--------|--------|
| GoldGuard | yes | `/data` |
| OpenCodex | no | `/app/.opencodex` |
| Hermes | no | `/opt/data` |

Private URLs:

- `http://opencodex.railway.internal:10100`
- `http://hermes.railway.internal:8642`

Health: `/api/health/live` (alive) and `/api/health/ready` (database). One
GoldGuard writer replica only.

## 3. Paper qualification before Live

1. Run paper on PAXGUSDT cash spot.
2. Collect closed cycles, backups, fault evidence, UI suite.
3. `GET /api/qualification/latest` must show `ready_for_live_canary: false`
   until those probes exist. Do not override it.
4. Arm Live only after TOTP, preflight, and qualification pass. The arming
   phrase is operator-owned.

## 4. Telegram

Create a bot, set token + chat id, keep critical categories (emergency,
breaker, protection, live_arm) unmuted. `POST /api/telegram/test` sends only
when both are configured.

## 5. What this release does not claim

- Live is not armed.
- Profitability is not guaranteed.
- Empty ledgers stay empty until paper actually fills.
