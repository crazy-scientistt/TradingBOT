# Task 2 report — real paper runtime

## Scope completed
- Built `backend/goldguard/services/runtime.py` with `RuntimeStatus` and `TradingRuntime`.
- Wired FastAPI lifespan/runtime ownership in `backend/goldguard/web/app.py`.
- Replaced coordinator mock-shaped checklist/AI calls with typed gate requests in `backend/goldguard/services/coordinator.py`.
- Updated focused coordinator/e2e tests and added runtime integration coverage.

## Files and symbols
- `backend/goldguard/services/runtime.py`
  - `RuntimeStatus`
  - `TradingRuntime`
  - `_AsyncDecisionAdapter`
- `backend/goldguard/services/coordinator.py`
  - `DecisionOutcome.closed_trade`
  - `ChecklistGate`
  - `AiVetoGate`
  - `TradingCoordinator.scan_closed_candle(...)` typed `ChecklistInputs` / `DecisionRequest` path
- `backend/goldguard/web/app.py`
  - `get_trading_runtime()`
  - lifespan runtime construction
  - `/api/bot/start`
  - `/api/bot/pause`
  - `/api/bot/stop`
  - `/api/bot/status`
  - `/api/bot/kill-switch`
- `backend/tests/services/test_runtime.py`
  - runtime decision-chain integration
  - restart-safe halted-flag integration
- `backend/tests/services/test_coordinator.py`
  - typed checklist/veto fixtures + context snapshot
- `backend/tests/e2e/test_shadow_run.py`
  - typed checklist/veto fixtures + context snapshot

## Test-first evidence
- Initial focused run before implementation:
  - `$env:PYTHONPATH='backend'; .venv\Scripts\pytest.exe backend/tests/services/test_runtime.py -q`
  - failed with `AttributeError: module 'goldguard.web.app' has no attribute 'get_trading_runtime'`

## Verification
- `$env:PYTHONPATH='backend'; .venv\Scripts\pytest.exe backend/tests/services/test_runtime.py -q`
  - `2 passed, 1 warning in 1.87s`
- `$env:PYTHONPATH='backend'; .venv\Scripts\pytest.exe backend/tests/services/test_runtime.py backend/tests/services/test_coordinator.py backend/tests/broker/test_paper.py backend/tests/storage backend/tests/e2e/test_shadow_run.py -q`
  - `22 passed, 1 warning in 3.67s`
- `git diff --check`
  - no whitespace errors; only Git LF→CRLF warnings on touched files

## Concerns
- Runtime preflight is still minimal in this task: it assumes the local bootstrap candle store and default `SymbolFilters` are sufficient until the later data-truthfulness/bootstrap tasks replace the demo warmup path.
- The typed checklist path uses a bounded local `ContextSnapshot` derived from the processed candle/quote so production startup no longer depends on test-only mocks, but full macro/context sourcing still belongs to later tasks.
- AI veto wiring is optional and only activates when `GOLDGUARD_GATEWAY_BASE_URL` is configured; paper runtime remains safe without enabling live execution.
