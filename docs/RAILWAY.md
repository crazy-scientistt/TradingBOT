# Railway: bot + OpenCodex (two services, one repo)

Same GitHub repo. Two boxes. They talk on Railway's private network.

```
[ You ]  →  GoldGuard URL (the dashboard you already have)
                │
                │  private  http://opencodex.railway.internal:10100
                ▼
           OpenCodex  ← you paste Gemini / Antigravity / OpenRouter keys here once
```

Do **not** put provider keys on the GoldGuard service.

## 1. GoldGuard service (already running)

Keep the existing service. After this deploy, add/confirm these variables:

| Variable | Value |
|---|---|
| `OPENCODEX_BASE_URL` | `http://opencodex.railway.internal:10100` |
| `OPENCODEX_API_AUTH_TOKEN` | same random token as the OpenCodex service |
| `GOLDGUARD_ENVIRONMENT` | `production` |
| `GOLDGUARD_MODE` | `paper` |

Name the OpenCodex service **exactly** `opencodex` so the private hostname matches.

## 2. New OpenCodex service

In the same Railway project:

1. **New service → GitHub** → this same `TradingBOT` repo
2. **Root directory** = `gateway`
3. **Dockerfile** = `gateway/Dockerfile` (auto if root is `gateway`)
4. Variables:

| Variable | Value |
|---|---|
| `PORT` | `10100` |
| `OPENCODEX_API_AUTH_TOKEN` | long random string (generate once, paste on both services) |

5. **Volume** mounted at `/app/.opencodex` so keys survive redeploys
6. Generate a public domain on this service — that is the OpenCodex dashboard where you add providers

OpenCodex will not start without the token. That is intentional.

## 3. Add your providers (once)

Open the OpenCodex public URL. Log in with the token if asked.

Add, in this order:

1. **Google Gemini** using your **Google AI Studio API key** (this is the reliable server path)
2. Antigravity / Gemini 3.7 High if OpenCodex lists it and accepts a pasteable credential
3. Any other keys you already use locally (OpenRouter, etc.)

Antigravity login on your laptop is a Google session. It does **not** automatically copy to Railway. If the Antigravity provider needs a browser login that only works locally, use the AI Studio key on the server.

## 4. Pick models in GoldGuard

GoldGuard → **Providers**:

- Veto (trade yes/no)
- News (what the agent reads)
- Hermes (strategy research)

Each dropdown is filled from OpenCodex `GET /v1/models`. If you delete a provider in OpenCodex, it disappears here. No keys are typed in GoldGuard.

**Test connection → Save.** Paper Start stays blocked until this health check is green.

## 5. Why not one container?

The bot must not hold your model keys. OpenCodex is the key vault + model catalog. One crash/redeploy of the bot does not wipe provider logins if the OpenCodex volume is mounted.
