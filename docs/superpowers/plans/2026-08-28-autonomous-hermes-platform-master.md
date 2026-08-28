# Autonomous Hermes Trading Platform Master Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Deliver the approved autonomous Binance Spot and USD-M Futures platform, with Hermes learning through OpenCodex/Antigravity, deterministic risk and execution, truthful UI, Telegram, mandatory Paper qualification, and Railway-ready operations.

**Architecture:** Keep the existing repository and single `main` branch, but implement the platform through eight independently reviewable workstreams. GoldGuard remains the deterministic risk/execution owner; the prebuilt Hermes service is the isolated researcher/learner; OpenCodex is the only AI-provider authentication and routing boundary.

**Tech Stack:** Python 3.12, FastAPI, Pydantic 2, SQLite/WAL, httpx, websockets, Argon2, TOTP, pytest, Hypothesis, Ruff, mypy strict, React 19, TypeScript 5.9, Vite 7, Vitest 3, Playwright, Docker Compose, OpenCodex 2.33.0 initially, Railway.

**Spec:** `docs/superpowers/specs/2026-08-28-autonomous-hermes-trading-platform-design.md`

## Global Constraints

- Work only in `C:\Users\creat\Downloads\TradingBOT-Autonomous` on the existing `main` branch; do not create another branch.
- Never push GitHub, deploy Railway, or place a Live order. The user owns push, deployment, and Live arming.
- Preserve the current checkout at `C:\Users\creat\Downloads\TradingBOT` and all existing containers, ports, volumes, databases, OpenCodex configuration, and Hermes memory.
- Preserve current strategy behavior as `Legacy`; new logic lives behind `Autonomous` and optional `Micro-Trade` profiles.
- Spot execution is cash-only `PAXGUSDT`; no borrowing or leverage.
- Futures execution is Binance USD-M perpetuals, isolated margin, One-way Mode, and selected validated pairs; no cross margin or Binance Options.
- Hermes and all AI output are untrusted proposal sources. Only deterministic code sizes, validates, executes, reconciles, protects, promotes, rolls back, and mutates durable state.
- Binance, Telegram, session, backup, and provider secrets never enter frontend payloads, logs, prompts, notifications, fixtures, or commits.
- New entries fail closed on stale/uncertain data or dependencies; exits, protection, reconciliation, and emergency controls never wait on AI or web research.
- `1,000` Micro-Trade position cycles per rolling 24 hours is a ceiling, never a quota.
- Paper qualification is mandatory before first Live and for every learned strategy; profitability is never guaranteed.
- All financial values use `Decimal`/canonical strings across Python, storage, JSON, and TypeScript boundaries; binary floats do not own money calculations.
- Every task follows red-green-refactor, runs focused tests first, then the workstream suite, then commits one independently reviewable change.
- On Windows, pytest uses a fresh `--basetemp` under `$env:TEMP` and `-p no:cacheprovider`.
- Gate 1 Task 0 creates repository-local `.venv` and `frontend/node_modules`; activate `.\.venv\Scripts\Activate.ps1` before commands in later tasks.

---

## Plan Suite and Dependency Order

| Gate | Plan | Depends on | Deliverable |
|---|---|---|---|
| 1 | `2026-08-28-01-control-plane-security.md` | approved spec | persisted profile, auth/2FA/CSRF, audit, Live arming state |
| 2 | `2026-08-28-02-paper-execution-risk.md` | Gate 1 | multi-pair Paper Spot/Futures, portfolio risk, breakers, Micro-Trade |
| 3 | `2026-08-28-03-research-evidence.md` | Gates 1-2 | normalized multi-source evidence, scoring, caching, HOLD/degrade rules |
| 4 | `2026-08-28-04-hermes-learning.md` | Gates 1-3 | real Hermes service, OpenCodex routing, reflection/memory, candidate lifecycle |
| 5 | `2026-08-28-05-live-binance-execution.md` | Gates 1-4 | signed Spot/Futures adapters, idempotency, protection, reconciliation |
| 6 | `2026-08-28-06-dashboard-telegram.md` | Gates 1-5 | truthful responsive UI, settings, orders/positions/P&L, Telegram |
| 7 | `2026-08-28-07-qualification-reliability.md` | Gates 1-6 | qualification, fault injection, security, backup/restore, diagnostics |
| 8 | `2026-08-28-08-railway-release.md` | Gates 1-7 | isolated/production packaging, Railway manifests, runbooks, final audit |

## Execution Rules

1. Read the master, approved spec, and current gate plan before editing.
2. Confirm `git status --short` contains only already-reviewed work.
3. Implement one task using its failing test, focused pass, broader pass, and commit steps.
4. Run the gate review commands before moving to the next gate.
5. Record real failures and limitations; never convert a planned feature into a readiness claim.
6. Do not begin Gate 5 Live execution until Gates 1-4 are complete and reviewed.
7. Do not enable Live code paths with real credentials during automated or local diagnostic tests.
8. Do not begin Gate 8 release packaging until the full Gate 7 certification report passes.

## Spec Coverage Matrix

| Spec section | Owning plan/task |
|---|---|
| 1 Purpose and current audited baseline | Plan 01 Task 0; Master final definition |
| 2 Modes/products/autonomy/Micro-Trade | Plan 01 Tasks 1-2; Plan 02 Tasks 3-6 |
| 3 GoldGuard/Hermes/OpenCodex/isolation architecture | Plan 01 Tasks 0 and 6; Plan 04 Tasks 1-3; Plan 08 Tasks 1-2 |
| 4 Authority and safety boundary | Plan 01 Tasks 3-6; Plan 04 Task 2; Plan 05 Task 6; Plan 07 Task 5 |
| 5 One-time Settings/controls/Live arming | Plan 01 Tasks 1-5; Plan 06 Tasks 2-3 |
| 6 Trading lifecycle | Plan 02 Tasks 2-6; Plan 05 Tasks 2-6 |
| 7 Account-wide risk and rolling-loss breaker | Plan 02 Tasks 4 and 6; Plan 07 Tasks 2-3 |
| 8 Research and evidence | Plan 03 Tasks 1-5 |
| 9 Hermes learning, qualification, promotion, rollback | Plan 04 Tasks 2-6; Plan 07 Task 1 |
| 10 Reliability, idempotency, recovery, backups | Plan 02 Task 5; Plan 05 Tasks 4-5; Plan 07 Tasks 2-4 |
| 11 Security | Plan 01 Tasks 3-6; Plan 05 Task 1; Plan 07 Task 5; Plan 08 Task 3 |
| 12 Dashboard and truthful UX | Plan 06 Tasks 1-4 and 6 |
| 13 Telegram | Plan 06 Task 5; Plan 07 Tasks 2 and 6 |
| 14 Verification and acceptance | Plan 07 Tasks 1-6; Plan 08 Tasks 1 and 5 |
| 15 Delivery workstreams | This master dependency table and Gate ledger |
| 16 Non-goals/limitations | Global constraints in every plan; Plan 08 Tasks 3-5 |
| 17 One-time operation and rare intervention | Plan 06 Tasks 2-5; Plan 08 Tasks 3-4 |

## Gate Review Commands

Run from `C:\Users\creat\Downloads\TradingBOT-Autonomous`:

```powershell
$testBase = Join-Path $env:TEMP "pytest-goldguard-gate"
uv run pytest backend/tests -q -p no:cacheprovider --basetemp $testBase
uv run ruff check backend
uv run mypy backend/goldguard
npm --prefix frontend test
npm --prefix frontend run typecheck
npm --prefix frontend run build
docker compose -f docker-compose.autonomous.yml --env-file .env.autonomous config
git diff --check
git status --short
```

Expected: every command exits `0`; `git status --short` shows only the work intentionally waiting for its next commit.

## Gate Completion Ledger

- [ ] **Gate 1:** Control-plane/security plan completed, focused/full checks recorded, commits reviewed.
- [ ] **Gate 2:** Paper execution/risk plan completed, focused/full checks recorded, commits reviewed.
- [ ] **Gate 3:** Research/evidence plan completed, focused/full checks recorded, commits reviewed.
- [ ] **Gate 4:** Hermes/learning plan completed, actual Hermes-to-OpenCodex-to-Antigravity diagnostic recorded.
- [ ] **Gate 5:** Live connector plan completed against fakes/test environments only; no unauthorized real order.
- [ ] **Gate 6:** Dashboard/Telegram plan completed, desktop/mobile/all-tab evidence recorded.
- [ ] **Gate 7:** Qualification/reliability certification passes with fault, restart, security, and restore evidence.
- [ ] **Gate 8:** Railway/release artifacts and candid handoff completed; no push or deployment performed by Codex.

## Final Definition of Done

- [ ] All eight plan files have every task checked and corresponding local commits.
- [ ] The master gate review commands pass freshly.
- [ ] Isolated GoldGuard, Hermes, and OpenCodex services run together using unique local resources.
- [ ] Paper Spot and Futures complete order-to-reflection lifecycles using real public Binance data and simulated fills.
- [ ] Live broker/reconciliation/protection contracts pass deterministic fake-server and fault tests.
- [ ] Hermes invokes the selected Antigravity model through OpenCodex and preserves memory across restart.
- [ ] Paper qualification, promotion, Live canary eligibility, rollback, and quarantine are proven without unauthorized Live execution.
- [ ] Dashboard data is truthful; Telegram test and mandatory critical routes work.
- [ ] Backup/restore, startup reconciliation, stale-data watchdog, circuit breakers, security, and secret redaction pass.
- [ ] Railway manifests and runbooks identify exact services, secrets, volumes, health checks, and user-controlled deployment steps.
- [ ] Final report names completed work, remaining non-blocking limitations, exact verification evidence, and the user’s next push/deploy actions.
