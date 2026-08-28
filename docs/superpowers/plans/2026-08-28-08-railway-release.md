# Railway Packaging and Release Handoff Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Package the certified platform as three Railway services with private networking, durable volumes, sealed secrets, correct health/readiness, backups, and user-run deployment instructions, then produce a candid final handoff without pushing or deploying.

**Architecture:** GoldGuard is the only public service; OpenCodex and Hermes are private service dependencies with separate persistent volumes and service tokens. Each service has its own Railway manifest/build context, liveness/readiness contract, graceful shutdown, resource assumptions, and backup ownership.

**Tech Stack:** Docker multi-stage builds, Docker Compose, Railway service manifests/private networking/volumes, FastAPI health endpoints, official Hermes Agent image, OpenCodex gateway, PowerShell/Python release audit.

**Spec:** `docs/superpowers/specs/2026-08-28-autonomous-hermes-trading-platform-design.md`

## Global Constraints

- Codex does not push GitHub, create/modify Railway services, configure production secrets, deploy, or arm Live.
- Production starts with Live disarmed/pending qualification regardless of environment variable mistakes.
- GoldGuard app is public; OpenCodex/Hermes data planes are private and token-authenticated.
- App, OpenCodex, and Hermes have separate durable volumes and backup schedules.
- One GoldGuard writer replica owns SQLite/WAL; scaling beyond one requires a reviewed database architecture change.
- Provider/Binance/Telegram/TOTP/session/backup secrets are entered through secure Railway configuration, never chat or committed files.

---

### Task 1: Reproducible non-root images and build contracts

**Files:**
- Modify: `Dockerfile`
- Modify: `backend/Dockerfile`
- Modify: `gateway/Dockerfile`
- Modify: `gateway/package.json`
- Create: `backend/tests/e2e/test_image_contracts.py`
- Create: `scripts/verify_images.ps1`

**Interfaces:**
- GoldGuard image serves frontend/backend on `$PORT`, writes only to `/data`, and runs as a non-root UID.
- OpenCodex version is pinned in `gateway/package.json`; provider state writes only to `/app/.opencodex`.
- Hermes production image is the verified `nousresearch/hermes-agent` repository digest recorded by the release audit, command `gateway run`, volume `/opt/data`.

- [ ] **Step 1: Write failing Dockerfile contract tests**

```python
def test_backend_image_is_nonroot_and_port_driven(dockerfile_text: str) -> None:
    assert "USER " in dockerfile_text
    assert "${PORT" in dockerfile_text or "$PORT" in dockerfile_text
    assert "/data" in dockerfile_text


def test_gateway_dependency_is_exact(package_json: dict) -> None:
    version = package_json["dependencies"]["@bitkyc08/opencodex"]
    assert version == "2.33.0"
```

- [ ] **Step 2: Verify image contracts/build failures**

```powershell
$testBase = Join-Path $env:TEMP "pytest-goldguard-images-red"
uv run pytest backend/tests/e2e/test_image_contracts.py -q -p no:cacheprovider --basetemp $testBase
docker build -f backend/Dockerfile -t goldguard-autonomous-app:test .
docker build -f gateway/Dockerfile -t goldguard-autonomous-gateway:test gateway
```

- [ ] **Step 3: Implement deterministic image stages and verification script**

```powershell
$containers = @('goldguard-autonomous-app:test','goldguard-autonomous-gateway:test')
foreach ($imageName in $containers) {
  docker image inspect $imageName --format '{{json .Config.User}}'
}
```

Use `npm ci --ignore-scripts`, Python lock-resolved dependencies, no development dependency layer in final images, explicit health tooling, read-only source filesystem where practical, and graceful SIGTERM handling.

- [ ] **Step 4: Run builds and container smoke**

```powershell
uv run pytest backend/tests/e2e/test_image_contracts.py -q -p no:cacheprovider --basetemp (Join-Path $env:TEMP "pytest-goldguard-images-green")
powershell -ExecutionPolicy Bypass -File scripts/verify_images.ps1
```

- [ ] **Step 5: Commit**

```powershell
git add Dockerfile backend/Dockerfile gateway/Dockerfile gateway/package.json backend/tests/e2e/test_image_contracts.py scripts/verify_images.ps1
git commit -m "ops: harden reproducible service images"
```

### Task 2: Three-service Railway manifests and private network contract

**Files:**
- Create: `railway.app.toml`
- Modify: `gateway/railway.toml`
- Create: `hermes/railway.toml`
- Create: `backend/goldguard/web/routes/health.py`
- Modify: `backend/goldguard/web/app.py`
- Create: `docs/operations/railway-topology.md`
- Create: `backend/tests/e2e/test_railway_manifests.py`
- Create: `backend/tests/web/test_health_api.py`
- Deprecate: `railway.toml` with a comment pointing to service-specific manifests, or replace it with the app manifest if Railway project configuration requires root discovery.

**Interfaces:**
- App private dependencies: `http://opencodex.railway.internal:10100`, `http://hermes.railway.internal:8642`.
- App volume `/data`; OpenCodex volume `/app/.opencodex`; Hermes volume `/opt/data`.
- App health `/api/health/live` and readiness `/api/health/ready`; private services use their supported health endpoints.
- `/api/health/live` proves the process event loop responds; `/api/health/ready` proves database/schema and mandatory startup dependencies; `/api/diagnostics` owns trading-readiness blockers.

- [ ] **Step 1: Write failing topology tests**

```python
def test_railway_services_have_distinct_volumes(manifests) -> None:
    assert manifests.app.volume_mount == "/data"
    assert manifests.opencodex.volume_mount == "/app/.opencodex"
    assert manifests.hermes.volume_mount == "/opt/data"


def test_only_app_requires_public_domain(topology) -> None:
    assert topology.public_services == ("goldguard",)
    assert set(topology.private_services) == {"opencodex", "hermes"}


def test_alive_can_be_not_ready(client, degraded_database) -> None:
    assert client.get("/api/health/live").status_code == 200
    assert client.get("/api/health/ready").status_code == 503
```

- [ ] **Step 2: Verify manifest tests fail**

```powershell
$testBase = Join-Path $env:TEMP "pytest-goldguard-railway-red"
uv run pytest backend/tests/e2e/test_railway_manifests.py backend/tests/web/test_health_api.py -q -p no:cacheprovider --basetemp $testBase
```

- [ ] **Step 3: Add service-specific manifests and topology**

```toml
[build]
builder = "DOCKERFILE"
dockerfilePath = "backend/Dockerfile"

[deploy]
healthcheckPath = "/api/health/live"
healthcheckTimeout = 100
restartPolicyType = "ON_FAILURE"
restartPolicyMaxRetries = 10
```

The health router returns small typed responses without probing slow external sources on liveness. Readiness uses cached component state and returns `503` with reason codes when startup dependencies are not ready. The topology document names service IDs, private hostnames, build contexts, ports, volume mounts, readiness dependencies, and explicitly requires one app replica.

- [ ] **Step 4: Run manifest and Compose configuration checks**

```powershell
$testBase = Join-Path $env:TEMP "pytest-goldguard-railway-green"
uv run pytest backend/tests/e2e/test_railway_manifests.py backend/tests/web/test_health_api.py -q -p no:cacheprovider --basetemp $testBase
docker compose -f docker-compose.autonomous.yml --env-file .env.autonomous config
git diff --check
```

- [ ] **Step 5: Commit**

```powershell
git add railway.app.toml railway.toml gateway/railway.toml hermes/railway.toml backend/goldguard/web/routes/health.py backend/goldguard/web/app.py docs/operations/railway-topology.md backend/tests/e2e/test_railway_manifests.py backend/tests/web/test_health_api.py
git commit -m "ops: define private three-service railway topology"
```

### Task 3: Secret, volume, health, and backup operations matrix

**Files:**
- Create: `docs/operations/secrets-and-volumes.md`
- Create: `docs/operations/health-and-recovery.md`
- Modify: `.env.example`
- Modify: `gateway/README.md`
- Modify: `docs/RAILWAY.md`
- Test: `backend/tests/e2e/test_operations_docs.py`

**Interfaces:**
- Secret matrix identifies owner service, variable, purpose, rotation effect, and prohibited consumers.
- Volume matrix identifies mount, contents, backup method, restore order, and data-loss consequence.
- Health matrix distinguishes liveness/readiness/trading readiness/degraded entry block.

- [ ] **Step 1: Write failing documentation-contract tests**

```python
def test_secret_matrix_covers_every_runtime_secret(doc_text, environment_fields) -> None:
    for field in environment_fields.secret_names:
        assert f"`{field}`" in doc_text


def test_docs_never_instruct_pasting_token_into_chat(doc_text) -> None:
    assert "paste the token into chat" not in doc_text.lower()
```

- [ ] **Step 2: Verify missing matrices fail**

```powershell
$testBase = Join-Path $env:TEMP "pytest-goldguard-ops-docs-red"
uv run pytest backend/tests/e2e/test_operations_docs.py -q -p no:cacheprovider --basetemp $testBase
```

- [ ] **Step 3: Write exact secure configuration and recovery instructions**

The secret matrix covers Binance key/secret, OpenCodex data/admin tokens, Antigravity account import inside OpenCodex, Hermes bridge token, Telegram bot token/chat ID, admin password bootstrap, TOTP encryption/seed handling, session secret, backup encryption key, CORS origins, and internal URLs. It states that laptop Antigravity login does not automatically transfer to Railway.

- [ ] **Step 4: Run docs/secret scan**

```powershell
$testBase = Join-Path $env:TEMP "pytest-goldguard-ops-docs-green"
uv run pytest backend/tests/e2e/test_operations_docs.py -q -p no:cacheprovider --basetemp $testBase
uv run python scripts/scan_secrets.py --repository .
git diff --check
```

- [ ] **Step 5: Commit**

```powershell
git add docs/operations/secrets-and-volumes.md docs/operations/health-and-recovery.md .env.example gateway/README.md docs/RAILWAY.md backend/tests/e2e/test_operations_docs.py
git commit -m "docs: define secure railway operations"
```

### Task 4: User runbooks for setup, Paper qualification, Live arming, incidents, and rollback

**Files:**
- Create: `docs/operations/first-time-setup.md`
- Create: `docs/operations/paper-qualification.md`
- Create: `docs/operations/live-arming.md`
- Create: `docs/operations/incidents.md`
- Create: `docs/operations/hermes-learning.md`
- Modify: `README.md`
- Test: `backend/tests/e2e/test_runbook_contracts.py`

**Interfaces:**
- First-time path: deploy services/volumes/secrets, configure OpenCodex Antigravity auth, test Hermes/model, configure Telegram, log in/2FA, save profile, start Paper.
- Qualification path explains exact thresholds and HOLD/Paper-only outcome.
- Live path uses completed app arming; never environment toggles or direct script orders.
- Incident paths cover protection failure, mismatch, stale data, breaker, provider outage, restart, revoked credentials, and backup restore.

- [ ] **Step 1: Write failing runbook coverage tests**

```python
@pytest.mark.parametrize("topic", [
    "Paper qualification", "Live arming", "Close All", "reconciliation",
    "OpenCodex", "Antigravity", "Hermes", "Telegram", "backup restore",
])
def test_runbooks_cover_operator_topics(all_runbooks: str, topic: str) -> None:
    assert topic.lower() in all_runbooks.lower()
```

- [ ] **Step 2: Verify runbook tests fail**

```powershell
$testBase = Join-Path $env:TEMP "pytest-goldguard-runbooks-red"
uv run pytest backend/tests/e2e/test_runbook_contracts.py -q -p no:cacheprovider --basetemp $testBase
```

- [ ] **Step 3: Write one-time and exceptional-intervention runbooks**

Each procedure lists prerequisites, exact UI/command action, expected state, stop condition, verification, and rollback. Never claim profit or guarantee 24/7 external dependencies.

- [ ] **Step 4: Run runbook and link checks**

```powershell
$testBase = Join-Path $env:TEMP "pytest-goldguard-runbooks-green"
uv run pytest backend/tests/e2e/test_runbook_contracts.py backend/tests/e2e/test_operations_docs.py -q -p no:cacheprovider --basetemp $testBase
git diff --check
```

- [ ] **Step 5: Commit**

```powershell
git add docs/operations README.md backend/tests/e2e/test_runbook_contracts.py
git commit -m "docs: hand off autonomous trading operations"
```

### Task 5: Final release audit and user-controlled handoff

**Files:**
- Modify: `scripts/audit_release.py`
- Create: `scripts/final_verification.ps1`
- Create: `docs/verification/final-handoff-template.md`
- Test: `backend/tests/e2e/test_release_audit.py`

**Interfaces:**
- Release audit verifies HEAD/worktree, one branch, no secrets, dependencies/locks, tests/static/build/browser, image/manifests, service diagnostics, qualification report, volumes/backups, and `real_orders_placed=0`.
- Handoff records completed/remaining/unverified truth and exact user push/deploy steps.

- [ ] **Step 1: Extend failing audit tests**

```python
def test_release_audit_requires_all_gate_artifacts(audit) -> None:
    result = audit.run(missing={"backup_restore_report"})
    assert result.ready is False
    assert "backup_restore_report" in result.blockers


def test_release_audit_refuses_dirty_or_extra_branch(repo) -> None:
    repo.create_untracked("unexpected.txt")
    assert ReleaseAudit(repo).run().ready is False
```

- [ ] **Step 2: Verify audit tests fail**

```powershell
$testBase = Join-Path $env:TEMP "pytest-goldguard-release-audit-red"
uv run pytest backend/tests/e2e/test_release_audit.py -q -p no:cacheprovider --basetemp $testBase
```

- [ ] **Step 3: Implement deterministic final verification orchestration**

```powershell
$ErrorActionPreference = 'Stop'
$testBase = Join-Path $env:TEMP "pytest-goldguard-final"
uv run pytest backend/tests -q -p no:cacheprovider --basetemp $testBase
uv run ruff check backend scripts
uv run mypy backend/goldguard
npm --prefix frontend test
npm --prefix frontend run typecheck
npm --prefix frontend run build
npm --prefix frontend run e2e
docker compose -f docker-compose.autonomous.yml --env-file .env.autonomous config
uv run python scripts/audit_release.py --require-zero-live-orders
git diff --check
git status --short
```

The script stops on the first failure and writes a redacted manifest of command/exit/evidence hashes. It does not push or deploy.

- [ ] **Step 4: Run Gate 8 final verification and inspect evidence**

```powershell
powershell -ExecutionPolicy Bypass -File scripts/final_verification.ps1
git log --oneline --decorate -20
git status -sb
```

Expected: verification exits `0`; only `main` exists locally; branch is ahead of `origin/main` by reviewed local commits; no remote mutation occurred.

- [ ] **Step 5: Commit the release audit and handoff template**

```powershell
git add scripts/audit_release.py scripts/final_verification.ps1 docs/verification/final-handoff-template.md backend/tests/e2e/test_release_audit.py
git commit -m "ops: finalize autonomous platform release audit"
```

After this commit, report the local commit range, tests, runtime evidence, remaining limitations, and the user's exact GitHub push and Railway deployment steps. Do not execute those external actions.
