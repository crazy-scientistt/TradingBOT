# Run OpenCodex locally on your PC

Paper-only. Live stays disarmed. You do not need Binance keys to confirm
OpenCodex, Hermes, and GoldGuard talk to each other.

## What you get

| Service | URL | Purpose |
|---------|-----|---------|
| GoldGuard | http://localhost:8000 | Paper cockpit and API |
| OpenCodex | http://localhost:10100 | AI gateway dashboard. Add Gemini / Antigravity here |
| Hermes | http://localhost:8642/health | Isolated researcher. Private on Railway; exposed here so you can probe it |

GoldGuard never stores provider keys. Keys live only in OpenCodex.

## Prerequisites

- Docker Desktop (Windows, macOS, or Linux)
- This repository cloned
- Optional: a Gemini / Google AI Studio key, entered in the OpenCodex dashboard (never committed)

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
existing file. Optional: add `GEMINI_API_KEY=...` to that file so OpenCodex
can list Gemini models on first boot. You can also paste the key later in
http://localhost:10100.

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

First start pulls the Hermes image and builds OpenCodex + GoldGuard. That can
take several minutes.

## Confirm it works

```bash
python scripts/verify_local_stack.py
```

Expected when OpenCodex is up:

- GoldGuard `/api/health/live` → alive
- GoldGuard `/api/health/ready` → ready
- OpenCodex `/healthz` → ok
- Hermes `/health` → ok (research degrades if this fails; paper trading still runs)
- `GET /api/diagnostics` lists OpenCodex / Hermes as pass or a named blocker
- `GET /api/providers/catalog` is empty until you add a provider in OpenCodex,
  then lists real model ids. It never invents models.

In the GoldGuard UI, open **Providers** and click **Test connection**.

## Add a model

1. Open http://localhost:10100
2. Sign in with the OpenCodex token from `.env.autonomous` (`OPENCODEX_API_AUTH_TOKEN`)
3. Add Google / Gemini / Antigravity
4. Refresh GoldGuard Providers. Models appear from `/v1/models`
5. Pick the same model for trade veto, news reader, and Hermes

Until a model exists, entries that need an AI veto fail closed. Protective
exits do not wait on AI.

## Native OpenCodex (no Docker) — optional

If Docker is unavailable you can run only the gateway:

```bash
cd gateway
export OPENCODEX_API_AUTH_TOKEN=dev-token
bun install
sh start.sh
```

Then point GoldGuard at `OPENCODEX_BASE_URL=http://127.0.0.1:10100`. Hermes
still needs Docker or a native Hermes install.

## Stop

```bash
docker compose -f docker-compose.local.yml --env-file .env.autonomous down
```

Volumes keep OpenCodex provider config and the paper ledger. Remove them only
if you want a clean slate:

```bash
docker compose -f docker-compose.local.yml --env-file .env.autonomous down -v
```

## What this does not do

- Does not arm Live
- Does not deploy Railway
- Does not require Telegram or Binance keys
- Does not claim profitability
