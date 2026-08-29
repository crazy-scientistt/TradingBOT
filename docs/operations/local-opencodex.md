# Run OpenCodex locally on your PC

**Development / paper only.** Live stays disarmed. You do not need Binance
trade keys to confirm OpenCodex, Hermes, and GoldGuard talk to each other.

This is the stack to test on your machine. The Grok preview desk is a
separate in-browser copy; Compose serves the GoldGuard UI at port 8000.

## What you get

| Service | URL | Purpose |
|---------|-----|---------|
| GoldGuard | http://localhost:8000 | Paper cockpit and API (bundled frontend) |
| OpenCodex | http://localhost:10100 | AI gateway. Add Antigravity / Gemini here |
| Hermes | http://localhost:8642/health | Isolated researcher |

Local paper envelope:

- Mode `paper`, `GOLDGUARD_LIVE_CAPABILITY_ENABLED=false`
- Starting book **100 USDT** (override with `GOLDGUARD_PAPER_STARTING_BALANCE`)
- Entries on **15m**, regime on **1h**
- Spot `PAXGUSDT` cash 1x
- Futures `BTCUSDT` + `SOLUSDT`, isolated, **≤2x** (ceiling is not the default)
- `ETHUSDT` new entries off
- Hermes SOUL: HOLD in chop, no 1h fade, cost gate, no orders

GoldGuard never stores provider keys. Keys live only in OpenCodex.

## Prerequisites

- Docker Desktop (Windows, macOS, or Linux)
- This repository cloned
- Optional: Antigravity Google login or a Gemini key in the OpenCodex dashboard (never committed)

## One-time env file

Windows PowerShell, from the repo root:

```powershell
powershell -ExecutionPolicy Bypass -File scripts/bootstrap_local_env.ps1
```

macOS / Linux:

```bash
sh scripts/bootstrap_local_env.sh
```

This creates `.env.autonomous` with random tokens. It will not overwrite an
existing file. Optional: add `GEMINI_API_KEY=...` so OpenCodex can list
Gemini models on first boot. You can also paste the key later at
http://localhost:10100.

If you already have `.env.autonomous` from an older checkout, add:

```
GOLDGUARD_PAPER_STARTING_BALANCE=100
GOLDGUARD_LIVE_CAPABILITY_ENABLED=false
GOLDGUARD_MODE=paper
```

## Start the three services

Windows:

```powershell
powershell -ExecutionPolicy Bypass -File scripts/start_local.ps1
```

macOS / Linux:

```bash
sh scripts/start_local.sh
```

Equivalent compose command:

```bash
docker compose -f docker-compose.local.yml --env-file .env.autonomous up --build
```

First start pulls Hermes and builds OpenCodex + GoldGuard. That can take several minutes.

## Confirm it works

```bash
python scripts/verify_local_stack.py
```

Expected:

- GoldGuard `/api/health/live` → alive
- GoldGuard `/api/health/ready` → ready
- OpenCodex `/healthz` → ok
- Hermes `/health` → ok (research degrades if this fails; paper trading still runs)
- `GET /api/diagnostics` lists OpenCodex / Hermes as pass or a named blocker
- `GET /api/providers/catalog` is empty until you add a provider in OpenCodex

In the GoldGuard UI: **Providers → Test connection**. Then **Start** paper.
Do not paste Binance secrets in chat.

## What is not ready

Live arming, Telegram, TOTP, and sealed holdout. Qualify will HOLD those on
purpose. Overnight paper on 15m is the local test, not a 1m trade quota.
