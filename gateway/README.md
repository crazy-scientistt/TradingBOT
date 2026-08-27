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

```bash
export OPENCODEX_API_AUTH_TOKEN=dev-token
docker compose up gateway
```

Dashboard: `http://localhost:10100`  
Header the bot sends: `x-opencodex-api-key: dev-token`

## Railway

Create a **second service** in the same project, root directory `gateway`.
See [docs/RAILWAY.md](../docs/RAILWAY.md).
