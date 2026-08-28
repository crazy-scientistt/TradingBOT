# Isolated Baseline — 2026-08-28

- Repository: `C:\Users\creat\Downloads\TradingBOT-Autonomous`
- Baseline-command checkout: `main` at `8328a53995197bdafdcdf8f5cc7af80442bdbd02` (plan commits were present when baseline commands ran)
- Final Task 0 head after the initial isolation fix: `346df427da153032a1cf277904a791f895173058`
- Source HEAD before plan commits: `c899c35e08ec8975766a14914d99b901501300ee`
- Existing checkout confirmed unchanged: `95b03dcdcde21ede2c5cd6bcccb77037a61270d8`
- Initial dependency isolation: `.venv` and `frontend\node_modules` were absent; Git status was clean before Task 0 edits.

## Environment provenance

- Python launcher: `C:\WINDOWS\py.exe`, `py -3.12` resolved to Python `3.12.8` at `C:\Users\creat\AppData\Local\Programs\Python\Python312\python.exe`.
- Repository-local Python environment: `.venv`; dependencies synchronized from `uv.lock` with `uv 0.12.7`. The `uv run` checks below were invoked through `.venv\Scripts\uv.exe` directly because uv was not on the global PATH.
- Frontend dependencies: `npm ci` from `frontend\package-lock.json` using Node `v24.13.0` and npm `11.6.2` (205 packages, 0 vulnerabilities; one upstream deprecation warning).
- Docker CLI: `29.2.0`; the Docker Desktop Linux daemon was unavailable for container listing.

## Verification results

| Command | Exit code | Result and actionable failure |
|---|---:|---|
| `py -3.12 -m venv .venv` | 0 | Passed; repository-local environment created. |
| `.venv\Scripts\python.exe -m pip install --disable-pip-version-check "uv>=0.8,<1"` | 0 | Passed; installed uv `0.12.7` into `.venv`. |
| `.venv\Scripts\uv.exe sync --all-groups --frozen` | 0 | Passed; synchronized locked packages. |
| `npm --prefix frontend ci` | 0 | Passed; lockfile install completed with one deprecation warning. |
| `powershell -ExecutionPolicy Bypass -File scripts/bootstrap_local_env.ps1` (first run) | 0 | Passed; created ignored `.env.autonomous` with development/Paper defaults, generated session/OpenCodex/Hermes tokens, and left Binance/Telegram fields empty. Output contained status only. |
| `.venv\Scripts\uv.exe run pytest backend/tests -q -p no:cacheprovider --basetemp C:\Users\creat\AppData\Local\Temp\pytest-goldguard-baseline-7b8ebff4f8ee4b1d9b17c5e2191a9b2e` | 2 | **Source/test collection failure:** `backend/tests/e2e/test_release_audit.py` imports `scripts.audit_release`, but `scripts` is not importable under the configured pytest import mode (`ModuleNotFoundError`). One Starlette/httpx deprecation warning also appeared. |
| `.venv\Scripts\uv.exe run ruff check backend` | 1 | **Source lint failures:** 20 existing violations across `context/calendar.py`, `context/sources.py`, `domain/defaults.py`, `market/live_stream.py`, `risk/engine.py`, `services/ingestion.py`, and `web/app.py` (line length, import ordering, task references, and unused variables). |
| `.venv\Scripts\uv.exe run mypy backend/goldguard` | 1 | **Source typing failures:** unexpected `include_open` keyword in `services/ingestion.py`; `rows` redefinition in `web/app.py`. |
| `npm --prefix frontend test` | 1 | **Source/UI test failures:** 3 failed and 9 passed tests across 4 files. Failures were duplicate `opencodex` text matching in `RouteMatrix`, missing `Win Rate` after Strategy Studio backtest, and an unhandled `matchMedia` error from `lightweight-charts` in jsdom. |
| `npm --prefix frontend run typecheck` | 0 | Passed. |
| `npm --prefix frontend run build` | 0 | Passed; Vite production build completed. |
| `docker compose -f docker-compose.autonomous.yml --env-file .env.autonomous.example config` | 0 | Passed; rendered project `goldguard-autonomous`, ports `18000`/`18100`, project-scoped volumes/network, and no containers were started. |

The additional consistency check `uv lock --check` returned exit code `1` because the committed lockfile needs an update for the current `pyproject.toml`; the lockfile was intentionally left unchanged because Task 0 commits only the five approved deliverables. This is a dependency-metadata baseline finding, not a repaired source change.

## Safety checks

- `git diff --check` returned exit code `0`.
- `git status --short --ignored` showed `.venv/`, `frontend/node_modules/`, and `.env.autonomous` only as ignored paths; none are staged or tracked.
- `docker ps -a --format '{{.Names}}'` returned exit code `1` because the Docker Desktop Linux daemon is not running. Compose `config` is non-mutating and therefore did not create a container; a live daemon is still required for empirical container-list verification.
- No provider, Binance, Telegram, Railway, or user credential values were read or included in this evidence.
- The reviewer fix adds the root `.dockerignore`; its patterns cover `.git/`, `.env*`, `.venv/`, dependency/build/cache/data/report/SDD artifacts while leaving `pyproject.toml`, frontend lock/package files, `frontend/`, `backend/`, `scripts/`, `app.py`, `main.py`, and gateway runtime inputs available to the Dockerfiles.
- The bootstrap target is anchored to the Autonomous repository via `$PSScriptRoot`. Invocation from an unrelated temporary working directory refused the existing repository `.env.autonomous` and left no temporary `.env.autonomous` file. A concurrent create test against a disposable script/repository copy produced exactly one create and one `FileMode.CreateNew` refusal; generated token values were checked only by length (44 characters), external credential fields remained empty, and no values were printed.
- Docker config validation remains non-mutating; the Docker Desktop Linux daemon was unavailable for empirical container-list verification.

## Runtime claims not proven by this baseline

Live execution, Futures execution, a real Hermes service, reconciliation, Telegram delivery, authentication/2FA, restart recovery, provider-account setup, Binance credentials, and any production or Railway behaviour remain unverified. The Docker daemon was unavailable, so container listing/build/health/restart evidence is still required.
