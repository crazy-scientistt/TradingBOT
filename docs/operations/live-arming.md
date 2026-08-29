# Live arming

Default state is **DISARMED**. Environment variables cannot silently arm Live.

Arming requires all of:

1. Authenticated operator + recent TOTP
2. Paper qualification `ready_for_live_canary`
3. Binance preflight: server time, trading enabled, withdrawals/transfers off
4. Reconciliation ready (no unknown external positions/orders)
5. Protection available for owned inventory
6. Explicit confirmation phrase from the operator

Spot is cash-only PAXGUSDT. Futures, if enabled later, is isolated one-way only.

On timeout: query by client order id. Never guess a fill. Never adopt unknown
manual orders.
