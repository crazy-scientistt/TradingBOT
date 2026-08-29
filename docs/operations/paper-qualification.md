# Paper qualification

Live canary is blocked until paper evidence exists. `GET /api/qualification/latest`
is fail-closed: missing probes are `*_NOT_READY`, never auto-pass.

Minimum paper bar (operator-run, not a promise of edge):

- Closed paper cycles recorded in the ledger (target 200, not a quota to grind)
- At least two observed regimes
- Rolling-loss breaker exercised in tests, not in hope
- Backup/restore drill into an empty temp target
- Telegram critical route tested
- UI suite recorded on desktop and mobile
- No fabricated fills, scores, or seeded trades

Hermes proposals stay `candidate` until this bar is met. Sealed holdout stays
sealed.
