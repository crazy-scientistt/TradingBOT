# Operator handoff

Code for all eight phases is in `main`. The items below cannot be finished
without credentials or a production account you control. Live stays disarmed
until you complete them.

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
