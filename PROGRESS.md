# TradingBOT Autonomous — Progress Report

> Generated: 2026-08-29
> Repo: https://github.com/crazy-scientistt/TradingBOT
> Honest status: All eight phases have code on `main`. Live is **not** armed.
> Profitability is **not** claimed. Operator secrets / Railway deploy remain.

---

## Phase status

| Phase | Name | Code | Gate closed? |
|-------|------|------|--------------|
| 1 | Control plane | Yes | Yes for paper |
| 2 | Paper risk | Yes | Yes for paper |
| 3 | Research / evidence | Yes — empty without clients, no invented timestamps/assets, HOLD on forum/stale/injection | Needs real HTTP clients |
| 4 | Hermes | Yes — bearer bridge, bound tools on real stores, holdout sealed, OpenAI-compatible OpenCodex route | Needs live Hermes/OpenCodex process |
| 5 | Live Binance | Yes — parse fills, query-on-timeout, httpx transport, fail-closed preflight | Live remains **disarmed** |
| 6 | Dashboard / Telegram | Yes — truthful empty envelopes, telegram test route, OpenCodex/Hermes diagnostics in UI | Needs bot token |
| 7 | Qualification | Yes — fail-closed evaluate, probes optional, hashed backup, recovery tests | Not certified |
| 8 | Railway + local PC | Yes — manifests, topology, `docker-compose.local.yml`, verify script, operator handoff | **Not deployed** |

---

## Local OpenCodex on your PC

```powershell
powershell -ExecutionPolicy Bypass -File scripts/bootstrap_local_env.ps1
powershell -ExecutionPolicy Bypass -File scripts/start_local.ps1
python scripts/verify_local_stack.py
```

See `docs/operations/local-opencodex.md`.

## Operator leftovers (cannot be finished here)

1. Binance API keys (withdrawals/transfers off)
2. Telegram bot token + chat id
3. Railway deploy (public GoldGuard, private OpenCodex and Hermes, volumes, secrets)
4. Live arming after paper qualification — you confirm, the code will not auto-arm
5. Paste a Gemini / Antigravity key into the OpenCodex dashboard (never into chat)

See `docs/operations/operator-handoff.md`.

## What this is not

- Live is not armed.
- The system is not profitable-by-default.
- Empty orders/positions remain empty until paper actually trades.
