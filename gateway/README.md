# OpenCodex gateway for GoldGuard

This folder is a **second Railway service**, not part of the bot container.

OpenCodex is the only place API keys live. GoldGuard never stores Gemini /
Antigravity / OpenRouter keys. It only talks to this proxy with a shared
token and then **picks models** that OpenCodex already listed.

## What it does

- OpenAI-compatible API: `/healthz`, `/v1/models`, `/v1/chat/completions`
- Binds `0.0.0.0` so the bot can reach it on Railway private networking
- Requires `OPENCODEX_API_AUTH_TOKEN` (OpenCodex will not start without it)
- Provider config persists on the volume mounted at `/app/.opencodex`

## Local

Preferred: start the three-service stack from the repo root.

```powershell
powershell -ExecutionPolicy Bypass -File scripts/start_local.ps1
```

Dashboard: `http://localhost:10100`  
Header GoldGuard sends: `x-opencodex-api-key` plus `Authorization: Bearer`.

Standalone gateway only:

```bash
export OPENCODEX_API_AUTH_TOKEN=dev-token
docker compose -f docker-compose.local.yml --env-file .env.autonomous up opencodex
```

See [docs/operations/local-opencodex.md](../docs/operations/local-opencodex.md).

## Railway

Create a **second service** in the same project, root directory `gateway`.
See [docs/RAILWAY.md](../docs/RAILWAY.md).
