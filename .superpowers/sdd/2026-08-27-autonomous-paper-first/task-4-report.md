# Task 4 — Autonomous promotion and rollback report

## Scope

Completed the paper-only autonomous promotion/rollback path and the real FastAPI wiring.
Routine candidates are judged by deterministic development, validation, sealed holdout, and
shadow gates without human approval. Protective risk bounds remain monotonic: candidates that
widen stops, shrink targets, or loosen data-quality guards are quarantined. Live execution was
not enabled.

## TDD evidence

Before implementation, added three app-level tests in
`backend/tests/web/test_api_truthfulness.py` for:

1. Lifespan construction of `_hermes_loop` and `_promotion_controller`.
2. `/api/hermes/step` delegation to `HermesResearchLoop.step`.
3. Canary state exposure and controller observation from durable ledger measurements.

RED command/output:

```text
pytest -q backend/tests/web/test_api_truthfulness.py -k 'lifespan_constructs or delegates_to_the_constructed_loop or exposes_canary'
3 failed, 20 deselected
AttributeError: module 'goldguard.web.app' has no attribute '_hermes_loop'
AttributeError: module 'goldguard.web.app' has no attribute '_promotion_controller'
```

After implementation (GREEN):

```text
pytest -q backend/tests/services/test_promotion_controller.py backend/tests/hermes/test_loop.py backend/tests/web/test_api_truthfulness.py
42 passed
```

## Implementation

- `backend/goldguard/services/promotion_controller.py`: autonomous gate sequencing, risk-bound
  rejection, durable canary open/close, rollback to the baseline, and circuit-breaker recording;
  fixed the existing E501 line in `_run_gates`.
- `backend/goldguard/hermes/loop.py`: autonomy kill switch and promotion-controller handoff.
- `backend/goldguard/storage/schema.sql`: durable `promotion_canary` and `autonomy_state`
  tables.
- `backend/goldguard/storage/repositories.py`: measured risk inputs, durable runtime-error
  counting, promotion/canary persistence, and autonomy persistence.
- `backend/goldguard/services/coordinator.py`: risk breakers now consume measured ledger inputs.
- `backend/goldguard/web/app.py`: lifespan constructs the controller and Hermes loop from shared
  durable repositories; Hermes step requires verified ingestion data and invokes the loop; bot
  status exposes current canary state and drives `on_canary_event` from measured equity,
  drawdown, trades, and durable health events.
- Tests updated/added in Hermes, coordinator, repository, runtime, promotion-controller, and web
  suites.

## Verification

```text
pytest -q
267 passed in 36.15s

.venv\\Scripts\\ruff.exe check backend
All checks passed!

.venv\\Scripts\\mypy.exe backend/goldguard/services/promotion_controller.py backend/goldguard/web/app.py backend/goldguard/hermes/loop.py backend/goldguard/storage/repositories.py
Success: no issues found in 4 source files

git diff --check
clean (only Git LF/CRLF warnings)
```

## Concerns / remaining risks

- The application can only promote after real verified candles and sufficient measured paper
  shadow history exist; an empty/new account correctly rejects the shadow gate.
- Runtime error thresholds count durable `system_health_events`; code paths that do not persist a
  health event cannot contribute to the error budget.
- No live exchange order path was enabled or exercised.
