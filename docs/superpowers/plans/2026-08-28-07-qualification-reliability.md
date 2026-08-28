# Qualification and Reliability Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Certify the integrated platform through deterministic qualification, fault injection, restart recovery, security/redaction, backup/restore, and real isolated-service diagnostics before it can be called ready for user-controlled deployment or Live canary arming.

**Architecture:** A release-certification service aggregates immutable reports from every subsystem; a fault harness injects boundary failures through fakes/proxies; backup and restore operate on copied/encrypted artifacts; diagnostics exercise the actual isolated GoldGuard, Hermes, and OpenCodex services without real orders.

**Tech Stack:** Python 3.12, pytest, Hypothesis, httpx fake transports, asyncio fault proxies, SQLite integrity/backup APIs, Docker Compose, Playwright, Ruff, mypy strict.

**Spec:** `docs/superpowers/specs/2026-08-28-autonomous-hermes-trading-platform-design.md`

## Global Constraints

- Certification is evidence, not a feature flag or profitability promise.
- No task places a real order; Live execution uses deterministic fake exchange contracts.
- A log line is not acceptance: tests assert state, order/protection result, entry block, audit record, UI status, and notification.
- Critical/high failures block readiness; non-blocking limitations remain explicit.
- Backups include no plaintext reportable secret and restore only into verified empty temporary targets during tests.

---

### Task 1: Immutable system qualification report

**Files:**
- Create: `backend/goldguard/release/__init__.py`
- Create: `backend/goldguard/release/models.py`
- Create: `backend/goldguard/release/qualification.py`
- Create: `backend/goldguard/storage/migrations/009_release_reports.sql`
- Create: `backend/goldguard/web/routes/qualification.py`
- Test: `backend/tests/release/test_qualification.py`
- Test: `backend/tests/web/test_qualification_api.py`

**Interfaces:**
- `SystemQualificationService.evaluate(now) -> SystemQualificationReport`.
- Gates: profile/security, Paper evidence, strategy statistics, data/evidence, risk/breaker, broker/protection, reconciliation, provider/Hermes, Telegram, backup/restore, fault suite, UI suite.
- Report is canonical, hashed, immutable, and exposes failures without secret internals.

- [ ] **Step 1: Write failing complete-gate tests**

```python
def test_one_failed_gate_blocks_live_eligibility(service) -> None:
    report = service.evaluate_with(overrides={"reconciliation": "fail"})
    assert report.ready_for_live_canary is False
    assert report.blockers == ("RECONCILIATION_NOT_READY",)


def test_report_hash_is_stable(service) -> None:
    assert service.evaluate(FIXED_NOW).report_hash == service.evaluate(FIXED_NOW).report_hash
```

- [ ] **Step 2: Verify failures**

```powershell
$testBase = Join-Path $env:TEMP "pytest-goldguard-certification-red"
uv run pytest backend/tests/release/test_qualification.py backend/tests/web/test_qualification_api.py -q -p no:cacheprovider --basetemp $testBase
```

- [ ] **Step 3: Implement report aggregation and immutable API**

```python
@dataclass(frozen=True)
class QualificationGateResult:
    gate: str
    status: Literal["pass", "fail", "unavailable"]
    evidence_ids: tuple[str, ...]
    reason_codes: tuple[str, ...]


@dataclass(frozen=True)
class SystemQualificationReport:
    report_hash: str
    observed_at: datetime
    gates: tuple[QualificationGateResult, ...]
    ready_for_live_canary: bool
    blockers: tuple[str, ...]
```

`GET /api/qualification/latest` reports status; reruns are explicit authenticated mutations and never auto-pass missing evidence.

- [ ] **Step 4: Run release/web/storage checks**

```powershell
$testBase = Join-Path $env:TEMP "pytest-goldguard-certification-green"
uv run pytest backend/tests/release backend/tests/web/test_qualification_api.py backend/tests/storage -q -p no:cacheprovider --basetemp $testBase
uv run ruff check backend/goldguard/release backend/goldguard/web/routes/qualification.py backend/tests/release
uv run mypy backend/goldguard/release backend/goldguard/web/routes/qualification.py
```

- [ ] **Step 5: Commit**

```powershell
git add backend/goldguard/release backend/goldguard/storage/migrations/009_release_reports.sql backend/goldguard/web/routes/qualification.py backend/tests/release backend/tests/web/test_qualification_api.py
git commit -m "feat: aggregate immutable release qualification"
```

### Task 2: Boundary fault-injection harness

**Files:**
- Create: `backend/tests/faults/fake_exchange.py`
- Create: `backend/tests/faults/fake_gateway.py`
- Create: `backend/tests/faults/fake_telegram.py`
- Create: `backend/tests/faults/test_network_and_exchange_faults.py`
- Create: `backend/tests/faults/test_ai_and_notification_faults.py`
- Create: `backend/tests/faults/test_data_faults.py`

**Interfaces:**
- Deterministic scenarios: disconnect, latency, timeout-after-accept, duplicate event, rate limit, stale/gap/duplicate data, clock drift, partial fill, reject, cancel failure, protection failure, Hermes/OpenCodex/provider/Telegram/source outage, malformed/injected model/evidence.
- Each scenario records expected safety outcome in its test name and assertions.

- [ ] **Step 1: Write failing cross-boundary scenarios**

```python
async def test_timeout_after_accept_does_not_duplicate_order(fault_system) -> None:
    result = await fault_system.run("timeout_after_accept")
    assert result.exchange_order_count == 1
    assert result.ledger_order_count == 1


async def test_gateway_outage_holds_entries_but_stop_executes(fault_system) -> None:
    result = await fault_system.run("opencodex_down_with_open_position")
    assert result.new_entry_action == "HOLD"
    assert result.position_exit_reason == "STOP_LOSS"
```

- [ ] **Step 2: Run and confirm missing harness failures**

```powershell
$testBase = Join-Path $env:TEMP "pytest-goldguard-faults-red"
uv run pytest backend/tests/faults -q -p no:cacheprovider --basetemp $testBase
```

- [ ] **Step 3: Implement deterministic programmable fakes**

```python
@dataclass(frozen=True)
class FaultScript:
    accept_request: bool = True
    response_delay: timedelta = timedelta()
    disconnect_after_accept: bool = False
    duplicate_updates: int = 0
    partial_fill_fractions: tuple[Decimal, ...] = ()
```

Fakes expose captured non-secret requests and virtual-clock control. Tests never rely on arbitrary sleep.

- [ ] **Step 4: Run fault and related subsystem suites**

```powershell
$testBase = Join-Path $env:TEMP "pytest-goldguard-faults-green"
uv run pytest backend/tests/faults backend/tests/execution backend/tests/live backend/tests/context backend/tests/notifications -q -p no:cacheprovider --basetemp $testBase
uv run ruff check backend/tests/faults
uv run mypy backend/tests/faults
```

- [ ] **Step 5: Commit**

```powershell
git add backend/tests/faults
git commit -m "test: inject exchange ai and data failures"
```

### Task 3: Restart, crash, and recovery qualification

**Files:**
- Create: `backend/tests/recovery/test_restart_matrix.py`
- Create: `backend/tests/recovery/test_crash_points.py`
- Modify: `backend/goldguard/services/runtime_supervisor.py`
- Modify: `backend/goldguard/services/reconciliation_supervisor.py`
- Test: `backend/tests/e2e/test_persistent_restart.py`

**Interfaces:**
- Crash points: before intent persist, after intent/before submit, timeout after submit, partial fill before protection, protection installed before ledger update, canary before rollback, notification before outbox ack.
- Restart result always begins with entries blocked and returns ready only after integrity/reconciliation/protection/provider checks.

- [ ] **Step 1: Write failing crash-point matrix**

```python
@pytest.mark.parametrize("crash_point", [
    "after_intent", "after_submit", "after_partial_fill", "after_protection",
    "during_canary", "after_notification_send",
])
async def test_restart_converges_without_duplicate_side_effect(crash_point, recovery_system) -> None:
    before = await recovery_system.crash_at(crash_point)
    after = await recovery_system.restart_and_reconcile()
    assert after.entries_enabled_only_after_reconcile is True
    assert after.duplicate_orders == 0
    assert after.unprotected_owned_positions == 0
    assert after.audit_continuity_from == before.last_audit_id
```

- [ ] **Step 2: Verify failures**

```powershell
$testBase = Join-Path $env:TEMP "pytest-goldguard-recovery-red"
uv run pytest backend/tests/recovery backend/tests/e2e/test_persistent_restart.py -q -p no:cacheprovider --basetemp $testBase
```

- [ ] **Step 3: Make lifecycle ownership explicit**

```python
async def startup(self) -> None:
    self._entries.block("startup_reconciliation")
    self._database.require_integrity()
    report = await self._reconciliation.startup_reconcile()
    await self._protection.require_all_owned_positions_protected(report)
    self._entries.apply_readiness(report.readiness)
```

Shutdown drains new entry evaluation, persists/flushes intent state, leaves exchange protection active, closes streams, and records termination state.

- [ ] **Step 4: Run recovery/full runtime suites**

```powershell
$testBase = Join-Path $env:TEMP "pytest-goldguard-recovery-green"
uv run pytest backend/tests/recovery backend/tests/services backend/tests/live backend/tests/e2e/test_persistent_restart.py -q -p no:cacheprovider --basetemp $testBase
uv run ruff check backend/goldguard/services backend/tests/recovery
uv run mypy backend/goldguard/services
```

- [ ] **Step 5: Commit**

```powershell
git add backend/goldguard/services/runtime_supervisor.py backend/goldguard/services/reconciliation_supervisor.py backend/tests/recovery backend/tests/e2e/test_persistent_restart.py
git commit -m "test: prove crash-safe restart convergence"
```

### Task 4: Encrypted backup, integrity, and restore drill

**Files:**
- Modify: `pyproject.toml`
- Modify: `uv.lock`
- Create: `scripts/backup_state.py`
- Create: `scripts/restore_state.py`
- Create: `backend/goldguard/operations/__init__.py`
- Create: `backend/goldguard/operations/backups.py`
- Test: `backend/tests/operations/test_backups.py`
- Create: `docs/operations/backup-restore.md`

**Interfaces:**
- `BackupService.create(destination, encryption_key) -> BackupManifest` uses SQLite online backup, hashes, encrypts, and includes app DB plus separately exported non-plaintext Hermes/OpenCodex volume archives.
- `RestoreService.verify/archive/restore` refuses nonempty/unexpected targets, wrong hashes/keys, and schema downgrade.

- [ ] **Step 1: Write failing corruption/wrong-target tests**

Add `cryptography>=45,<47` to runtime dependencies and regenerate `uv.lock` with `uv lock`; backup encryption uses AES-256-GCM with a fresh nonce and authenticated manifest metadata.

```python
def test_corrupted_backup_never_restores(service, corrupted_archive, empty_target) -> None:
    with pytest.raises(BackupIntegrityError):
        service.restore(corrupted_archive, empty_target, key())


def test_restore_refuses_active_database(service, archive, active_target) -> None:
    with pytest.raises(RestoreTargetNotEmpty):
        service.restore(archive, active_target, key())
```

- [ ] **Step 2: Verify failures**

```powershell
$testBase = Join-Path $env:TEMP "pytest-goldguard-backups-red"
uv run pytest backend/tests/operations/test_backups.py -q -p no:cacheprovider --basetemp $testBase
```

- [ ] **Step 3: Implement online backup and verified restore**

```python
@dataclass(frozen=True)
class BackupManifest:
    created_at: datetime
    source_schema_version: int
    encrypted_sha256: str
    components: tuple[str, ...]
```

The CLI accepts explicit paths only, refuses workspace/home/root targets, uses a temporary staging directory, and never prints encryption keys. Tests restore into fresh `$env:TEMP` directories and run `PRAGMA integrity_check` plus representative record comparisons.

- [ ] **Step 4: Run backup/security checks**

```powershell
$testBase = Join-Path $env:TEMP "pytest-goldguard-backups-green"
uv run pytest backend/tests/operations/test_backups.py backend/tests/storage backend/tests/security -q -p no:cacheprovider --basetemp $testBase
uv run ruff check scripts/backup_state.py scripts/restore_state.py backend/goldguard/operations backend/tests/operations
uv run mypy backend/goldguard/operations
```

- [ ] **Step 5: Commit**

```powershell
git add pyproject.toml uv.lock scripts/backup_state.py scripts/restore_state.py backend/goldguard/operations backend/tests/operations/test_backups.py docs/operations/backup-restore.md
git commit -m "ops: verify encrypted state backup and restore"
```

### Task 5: Security, secret-redaction, and permission certification

**Files:**
- Create: `backend/tests/security/test_all_endpoints.py`
- Create: `backend/tests/security/test_secret_redaction_property.py`
- Create: `backend/tests/security/test_permissions.py`
- Create: `scripts/scan_secrets.py`
- Modify: `backend/goldguard/providers/redaction.py`
- Test: `backend/tests/e2e/test_security_boundary.py`

**Interfaces:**
- Property tests inject sentinel secrets into every secret-bearing configuration and assert absence from responses/logs/errors/audits/prompts/notifications/exports.
- Endpoint matrix verifies auth/CSRF/TOTP by method and sensitivity.
- Binance preflight fixture proves withdrawal/transfer permission causes Live failure.

- [ ] **Step 1: Write failing endpoint/redaction matrix**

```python
@pytest.mark.parametrize("path", MUTATING_ENDPOINTS)
def test_mutation_requires_auth_and_csrf(client, path) -> None:
    assert client.post(path, json={}).status_code in {401, 403}


@given(secret=sentinel_secrets())
def test_secret_absent_from_all_observable_surfaces(secret, security_system) -> None:
    surfaces = security_system.exercise(secret)
    assert all(secret not in surface for surface in surfaces)
```

- [ ] **Step 2: Run security failures**

```powershell
$testBase = Join-Path $env:TEMP "pytest-goldguard-security-cert-red"
uv run pytest backend/tests/security backend/tests/e2e/test_security_boundary.py -q -p no:cacheprovider --basetemp $testBase
```

- [ ] **Step 3: Centralize recursive redaction and permission matrix**

```python
def redact(value: object, secret_values: Collection[str]) -> object:
    if isinstance(value, str):
        result = value
        for secret in secret_values:
            result = result.replace(secret, "[REDACTED]")
        return result
    if isinstance(value, dict):
        return {key: redact(item, secret_values) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return type(value)(redact(item, secret_values) for item in value)
    return value
```

The scanner rejects known key patterns and committed `.env`/auth/account export files while allowlisting documented placeholders.

- [ ] **Step 4: Run security and secret scan**

```powershell
$testBase = Join-Path $env:TEMP "pytest-goldguard-security-cert-green"
uv run pytest backend/tests/security backend/tests/e2e/test_security_boundary.py -q -p no:cacheprovider --basetemp $testBase
uv run python scripts/scan_secrets.py --repository .
uv run ruff check backend/goldguard/providers/redaction.py backend/tests/security scripts/scan_secrets.py
```

- [ ] **Step 5: Commit**

```powershell
git add backend/tests/security backend/tests/e2e/test_security_boundary.py scripts/scan_secrets.py backend/goldguard/providers/redaction.py
git commit -m "security: certify endpoint and secret boundaries"
```

### Task 6: Actual isolated-service diagnostic and Gate 7 certification

**Files:**
- Create: `scripts/run_diagnostics.py`
- Create: `backend/tests/e2e/test_diagnostic_contract.py`
- Create: `docs/verification/diagnostic-report-template.md`
- Modify: `scripts/audit_release.py`

**Interfaces:**
- Diagnostic proves public Binance data, Paper Spot/Futures lifecycle, Hermes-to-OpenCodex selected model call, persistence after restart, candidate/evaluation/promotion/rollback, truthful UI APIs, Telegram test route, and backup/restore.
- Output is JSON plus Markdown summary with exact timestamps, component versions, checks, blockers, and redacted evidence IDs.

- [ ] **Step 1: Write failing diagnostic contract test**

```python
def test_diagnostic_report_contains_every_required_check(report) -> None:
    required = {
        "binance_public", "paper_spot", "paper_futures", "opencodex_model",
        "hermes_memory_restart", "promotion_rollback", "telegram_test",
        "database_restart", "backup_restore", "frontend_truthfulness",
    }
    assert required == set(report.checks)
    assert report.real_orders_placed == 0
```

- [ ] **Step 2: Verify diagnostic contract fails**

```powershell
$testBase = Join-Path $env:TEMP "pytest-goldguard-diagnostics-red"
uv run pytest backend/tests/e2e/test_diagnostic_contract.py -q -p no:cacheprovider --basetemp $testBase
```

- [ ] **Step 3: Implement fail-closed diagnostic orchestration**

```python
def main() -> int:
    report = DiagnosticRunner(load_safe_diagnostic_config()).run()
    write_redacted_reports(report)
    return 0 if report.passed and report.real_orders_placed == 0 else 1
```

The script refuses `execution_mode=live`, missing isolation prefix, nonlocal app URL, or real credential variables. It may use public Binance data and configured OpenCodex/Hermes/Telegram test delivery.

- [ ] **Step 4: Run Gate 7 full certification**

```powershell
docker compose -f docker-compose.autonomous.yml --env-file .env.autonomous config
docker compose -f docker-compose.autonomous.yml --env-file .env.autonomous up -d opencodex hermes backend
uv run python scripts/run_diagnostics.py --compose-project goldguard-autonomous-diagnostic
$testBase = Join-Path $env:TEMP "pytest-goldguard-gate7"
uv run pytest backend/tests -q -p no:cacheprovider --basetemp $testBase
uv run ruff check backend scripts
uv run mypy backend/goldguard
npm --prefix frontend test
npm --prefix frontend run typecheck
npm --prefix frontend run build
npm --prefix frontend run e2e
git diff --check
```

Expected: all commands exit `0`; diagnostic states `real_orders_placed=0`; the latest System Qualification Report passes every non-Live-execution gate.

- [ ] **Step 5: Commit**

```powershell
git add scripts/run_diagnostics.py scripts/audit_release.py backend/tests/e2e/test_diagnostic_contract.py docs/verification/diagnostic-report-template.md
git commit -m "test: certify autonomous platform reliability"
```
