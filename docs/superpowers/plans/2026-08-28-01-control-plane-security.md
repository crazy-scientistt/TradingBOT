# Control Plane and Security Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the durable one-time autonomous profile, authenticated admin control plane, TOTP/CSRF protection, immutable audit trail, and persisted Live-arming state required by every later workstream.

**Architecture:** Add focused domain, repository, service, and router modules around the existing FastAPI application without rewriting unrelated routes. Validate settings and runtime safety before activating an immutable profile version; keep provider/Binance/Telegram secrets outside profile payloads.

**Tech Stack:** Python 3.12, Pydantic 2, FastAPI, SQLite/WAL, Argon2, PyOTP 2.9, httpx test client, pytest, Hypothesis, Ruff, mypy strict.

**Spec:** `docs/superpowers/specs/2026-08-28-autonomous-hermes-trading-platform-design.md`

## Global Constraints

- Work on the existing local `main`; no push, deployment, or Live order.
- Money/rates are `Decimal` and serialized as strings.
- Profile settings contain configuration and status only, never secret material.
- Live arming is an application state; environment variables only provide capability/secrets.
- Persisted armed state resumes only after later reconciliation reports ready.
- All mutations require authenticated admin + CSRF; sensitive mutations additionally require recent TOTP.
- Existing Paper/Legacy runtime remains the safe default until later gates replace startup ownership.

---

### Task 0: Bootstrap isolated dependencies and record the real baseline

**Files:**
- Create: `.venv/` (ignored local environment; never commit)
- Create: `docker-compose.autonomous.yml`
- Create: `.env.autonomous.example`
- Create: `scripts/bootstrap_local_env.ps1`
- Create: `docs/verification/2026-08-28-isolated-baseline.md`
- Modify: `.gitignore`
- Verify: `pyproject.toml`, `uv.lock`, `frontend/package-lock.json`

**Interfaces:**
- Every later PowerShell session begins with `.\.venv\Scripts\Activate.ps1`.
- Python dependencies come from `uv.lock`; frontend dependencies come from `frontend/package-lock.json`.
- Baseline report records command, exit code, failure summary, checkout/HEAD, and explicitly separates missing dependency failures from source failures.
- All local containers use the `goldguard-autonomous` Compose project, host ports `18000` (app), `18100` (OpenCodex), and `18642` (Hermes when added), with project-scoped volumes/network.

- [ ] **Step 1: Prove the clone has no shared local dependencies**

```powershell
Test-Path -LiteralPath .venv
Test-Path -LiteralPath frontend\node_modules
git status --short
```

Expected: both dependency paths are `False`; Git status contains only the approved plan/spec work at plan-writing time and is clean when implementation begins.

Create `docker-compose.autonomous.yml` as a standalone Compose file; do not layer it over the existing file with fixed container names:

```yaml
name: goldguard-autonomous
services:
  opencodex:
    build: {context: ./gateway, dockerfile: Dockerfile}
    ports: ["18100:10100"]
    environment:
      PORT: "10100"
      OPENCODEX_API_AUTH_TOKEN: ${OPENCODEX_API_AUTH_TOKEN}
      OPENCODEX_ADMIN_AUTH_TOKEN: ${OPENCODEX_ADMIN_AUTH_TOKEN}
    volumes: ["autonomous-opencodex:/app/.opencodex"]
    networks: ["autonomous-net"]
  backend:
    build: {context: ., dockerfile: backend/Dockerfile}
    ports: ["18000:8000"]
    environment:
      GOLDGUARD_ENVIRONMENT: development
      GOLDGUARD_MODE: paper
      GOLDGUARD_DATA_DIR: /app/data
      OPENCODEX_BASE_URL: http://opencodex:10100
      OPENCODEX_API_AUTH_TOKEN: ${OPENCODEX_API_AUTH_TOKEN}
    depends_on: ["opencodex"]
    volumes: ["autonomous-ledger:/app/data"]
    networks: ["autonomous-net"]
volumes:
  autonomous-opencodex: {}
  autonomous-ledger: {}
networks:
  autonomous-net: {}
```

Add `!.env.autonomous.example` to `.gitignore` and commit this non-secret template:

```dotenv
GOLDGUARD_ENVIRONMENT=development
GOLDGUARD_MODE=paper
GOLDGUARD_DATA_DIR=/app/data
GOLDGUARD_SESSION_SECRET=
OPENCODEX_API_AUTH_TOKEN=
OPENCODEX_ADMIN_AUTH_TOKEN=
HERMES_BRIDGE_TOKEN=
BINANCE_API_KEY=
BINANCE_API_SECRET=
TELEGRAM_BOT_TOKEN=
TELEGRAM_CHAT_ID=
```

Keep `.env.autonomous` ignored. `scripts/bootstrap_local_env.ps1` refuses to overwrite an existing file, generates session/OpenCodex/Hermes tokens with `RandomNumberGenerator.GetBytes(32)`, writes the explicit target `.env.autonomous`, and prints only `created` status—not secret values. Binance and Telegram values stay empty until the user configures them through the approved secure setup.

- [ ] **Step 2: Create repository-local Python and frontend environments**

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install --disable-pip-version-check "uv>=0.8,<1"
.\.venv\Scripts\uv.exe sync --all-groups --frozen
npm --prefix frontend ci
powershell -ExecutionPolicy Bypass -File scripts/bootstrap_local_env.ps1
```

Expected: commands exit `0`; no global Python package, existing project environment, or external `node_modules` is modified.

- [ ] **Step 3: Run the complete baseline commands and capture exact outcomes**

```powershell
.\.venv\Scripts\Activate.ps1
$testBase = Join-Path $env:TEMP "pytest-goldguard-baseline"
uv run pytest backend/tests -q -p no:cacheprovider --basetemp $testBase
uv run ruff check backend
uv run mypy backend/goldguard
npm --prefix frontend test
npm --prefix frontend run typecheck
npm --prefix frontend run build
docker compose -f docker-compose.autonomous.yml --env-file .env.autonomous.example config
```

Expected: each command produces a real source/dependency result. Do not describe a failing command as passing; copy concise failure counts and first actionable errors into the baseline report.

- [ ] **Step 4: Write and verify the baseline report**

```markdown
# Isolated Baseline — 2026-08-28

- Repository: `C:\Users\creat\Downloads\TradingBOT-Autonomous`
- Source HEAD before plan commits: `c899c35e08ec8975766a14914d99b901501300ee`
- Existing checkout confirmed unchanged: `95b03dcdcde21ede2c5cd6bcccb77037a61270d8`
- Python environment: `.venv` created from Python 3.12 and synchronized from `uv.lock`
- Frontend environment: `npm ci` from `frontend/package-lock.json`
- Verification table: one row per command with exit code, pass/fail count, and actionable failures
- Runtime claims not proven by baseline: Live execution, Futures, real Hermes service, reconciliation, Telegram, auth/2FA, restart recovery
```

Run `git diff --check`; confirm `.venv/` and `frontend/node_modules/` do not appear in `git status --short`; confirm `docker ps -a --format '{{.Names}}'` contains no container created by the baseline config-only command.

- [ ] **Step 5: Commit the evidence report only**

```powershell
git add .gitignore docker-compose.autonomous.yml .env.autonomous.example scripts/bootstrap_local_env.ps1 docs/verification/2026-08-28-isolated-baseline.md
git commit -m "chore: isolate autonomous local workspace"
```

### Task 1: Versioned autonomous profile domain and migration

**Files:**
- Create: `backend/goldguard/domain/profile.py`
- Create: `backend/goldguard/storage/migrations/003_control_plane.sql`
- Modify: `backend/goldguard/storage/database.py`
- Modify: `backend/goldguard/domain/enums.py`
- Test: `backend/tests/domain/test_profile.py`
- Test: `backend/tests/storage/test_control_plane_migration.py`

**Interfaces:**
- Produces: `ExecutionMode`, `StrategyMode`, `AutonomousProfileKind`, `ProductKind`, `RiskCeilings`, `NotificationPreferences`, `AutonomousProfile`.
- Produces storage tables: `profile_versions`, `active_profile`, `live_arming_state`, `admin_users`, `admin_sessions`, `security_events`.
- Migration runner: `Database.migrate()` applies numbered SQL files once after the current base schema.

- [ ] **Step 1: Write failing domain and migration tests**

```python
def test_profile_applies_one_risk_envelope_to_paper_and_live() -> None:
    profile = AutonomousProfile.model_validate({
        "execution_mode": "paper",
        "strategy_mode": "autonomous",
        "autonomous_profile": "micro_trade",
        "spot_enabled": True,
        "futures_enabled": True,
        "spot_pairs": ["PAXGUSDT"],
        "futures_pairs": ["BTCUSDT", "ETHUSDT"],
        "risk": {
            "max_capital_per_trade_rate": "0.005",
            "max_futures_leverage": 5,
            "max_total_exposure_rate": "0.20",
            "rolling_24h_loss_limit_rate": "0.03",
        },
    })
    assert profile.risk.max_futures_leverage == 5
    assert profile.spot_pairs == ("PAXGUSDT",)


def test_migration_003_is_idempotent(database: Database) -> None:
    database.migrate()
    database.migrate()
    with database.connect() as connection:
        count = connection.execute(
            "SELECT COUNT(*) FROM schema_migrations WHERE version = 3"
        ).fetchone()[0]
    assert count == 1
```

- [ ] **Step 2: Run tests and confirm the missing types/migration fail**

```powershell
$testBase = Join-Path $env:TEMP "pytest-goldguard-profile-red"
uv run pytest backend/tests/domain/test_profile.py backend/tests/storage/test_control_plane_migration.py -q -p no:cacheprovider --basetemp $testBase
```

Expected: collection/import failure for `goldguard.domain.profile` or missing migration version `3`.

- [ ] **Step 3: Implement bounded profile types and numbered migrations**

```python
class ExecutionMode(StrEnum):
    PAPER = "paper"
    LIVE = "live"


class ProductKind(StrEnum):
    SPOT = "spot"
    FUTURES = "futures"


class RiskCeilings(BaseModel):
    model_config = ConfigDict(frozen=True)
    max_capital_per_trade_rate: Decimal = Field(gt=Decimal("0"), le=Decimal("1"))
    max_futures_leverage: int = Field(ge=1, le=125)
    max_total_exposure_rate: Decimal = Field(gt=Decimal("0"), le=Decimal("1"))
    rolling_24h_loss_limit_rate: Decimal = Field(gt=Decimal("0"), le=Decimal("1"))


class AutonomousProfile(BaseModel):
    model_config = ConfigDict(frozen=True)
    execution_mode: ExecutionMode
    strategy_mode: StrategyMode
    autonomous_profile: AutonomousProfileKind
    spot_enabled: bool
    futures_enabled: bool
    spot_pairs: tuple[str, ...]
    futures_pairs: tuple[str, ...]
    risk: RiskCeilings
    notifications: NotificationPreferences = NotificationPreferences()
```

`003_control_plane.sql` stores canonical profile JSON/hash, one active-profile pointer, a single Live-arming row (`disarmed`, `armed_pending_reconciliation`, `armed_ready`, `blocked`), password/TOTP metadata, expiring sessions, and immutable security/audit events. It must not include raw Binance, Telegram, or provider credentials.

- [ ] **Step 4: Run focused tests and static checks**

```powershell
$testBase = Join-Path $env:TEMP "pytest-goldguard-profile-green"
uv run pytest backend/tests/domain/test_profile.py backend/tests/storage/test_control_plane_migration.py backend/tests/storage/test_database.py -q -p no:cacheprovider --basetemp $testBase
uv run ruff check backend/goldguard/domain backend/goldguard/storage backend/tests/domain backend/tests/storage
uv run mypy backend/goldguard/domain backend/goldguard/storage
```

Expected: all commands exit `0`.

- [ ] **Step 5: Commit**

```powershell
git add backend/goldguard/domain/profile.py backend/goldguard/domain/enums.py backend/goldguard/storage/database.py backend/goldguard/storage/migrations/003_control_plane.sql backend/tests/domain/test_profile.py backend/tests/storage/test_control_plane_migration.py
git commit -m "feat: add durable autonomous profile schema"
```

### Task 2: Transactional profile repository and settings service

**Files:**
- Create: `backend/goldguard/storage/profile_repository.py`
- Create: `backend/goldguard/services/settings_service.py`
- Modify: `backend/goldguard/storage/__init__.py`
- Test: `backend/tests/storage/test_profile_repository.py`
- Test: `backend/tests/services/test_settings_service.py`

**Interfaces:**
- `ProfileRepository.active() -> ActiveProfile | None`
- `ProfileRepository.activate(profile: AutonomousProfile, actor: str, correlation_id: str) -> ActiveProfile`
- `SettingsService.preview(candidate: AutonomousProfile, runtime: RuntimeSafetySnapshot) -> SettingsPreview`
- `SettingsService.activate(candidate: AutonomousProfile, actor: str, correlation_id: str, runtime: RuntimeSafetySnapshot) -> ActiveProfile`
- `RuntimeSafetySnapshot` exposes `has_open_positions`, `has_open_entry_orders`, `live_armed`, and `account_equity_usdt`.

- [ ] **Step 1: Write failing validation-before-persistence tests**

```python
def test_rejected_balance_change_does_not_activate_profile(service, repository) -> None:
    before = repository.active()
    unsafe = RuntimeSafetySnapshot(
        has_open_positions=True,
        has_open_entry_orders=False,
        live_armed=False,
        account_equity_usdt=Decimal("1000"),
    )
    with pytest.raises(ProfileChangeBlocked, match="open position"):
        service.activate(candidate_profile(), "admin", "corr-1", unsafe)
    assert repository.active() == before


def test_preview_returns_live_usdt_equivalents(service) -> None:
    preview = service.preview(
        candidate_profile(),
        RuntimeSafetySnapshot(False, False, False, Decimal("10000")),
    )
    assert preview.max_capital_per_trade_usdt == Decimal("50.00")
```

- [ ] **Step 2: Verify failures**

```powershell
$testBase = Join-Path $env:TEMP "pytest-goldguard-settings-red"
uv run pytest backend/tests/storage/test_profile_repository.py backend/tests/services/test_settings_service.py -q -p no:cacheprovider --basetemp $testBase
```

Expected: missing repository/service imports.

- [ ] **Step 3: Implement canonical immutable activation**

```python
@dataclass(frozen=True)
class SettingsPreview:
    profile: AutonomousProfile
    max_capital_per_trade_usdt: Decimal
    max_total_exposure_usdt: Decimal
    rolling_24h_loss_limit_usdt: Decimal
    blockers: tuple[str, ...]


class SettingsService:
    def activate(self, candidate, actor, correlation_id, runtime):
        preview = self.preview(candidate, runtime)
        if preview.blockers:
            raise ProfileChangeBlocked("; ".join(preview.blockers))
        return self._repository.activate(candidate, actor, correlation_id)
```

Activation uses one database transaction to insert the immutable version, update the pointer, append an audit record, and move a Live-armed profile to `armed_pending_reconciliation` when its execution-affecting fields change.

- [ ] **Step 4: Run repository/service suites**

```powershell
$testBase = Join-Path $env:TEMP "pytest-goldguard-settings-green"
uv run pytest backend/tests/storage/test_profile_repository.py backend/tests/services/test_settings_service.py backend/tests/storage/test_repositories.py -q -p no:cacheprovider --basetemp $testBase
uv run ruff check backend/goldguard/storage backend/goldguard/services backend/tests/storage backend/tests/services
uv run mypy backend/goldguard/storage backend/goldguard/services
```

- [ ] **Step 5: Commit**

```powershell
git add backend/goldguard/storage/profile_repository.py backend/goldguard/storage/__init__.py backend/goldguard/services/settings_service.py backend/tests/storage/test_profile_repository.py backend/tests/services/test_settings_service.py
git commit -m "feat: activate settings transactionally"
```

### Task 3: Admin password, TOTP, sessions, and CSRF

**Files:**
- Modify: `pyproject.toml`
- Modify: `uv.lock`
- Create: `backend/goldguard/security/__init__.py`
- Create: `backend/goldguard/security/models.py`
- Create: `backend/goldguard/security/service.py`
- Create: `backend/goldguard/web/auth_dependencies.py`
- Test: `backend/tests/security/test_auth_service.py`
- Test: `backend/tests/security/test_auth_dependencies.py`

**Interfaces:**
- `AuthService.bootstrap_admin(password: SecretStr, totp_secret: SecretStr) -> None`
- `AuthService.login(password: SecretStr, ip: str, user_agent: str) -> SessionTokens`
- `AuthService.verify_totp(session_id: str, code: str) -> AuthSession`
- `AuthService.require_recent_totp(session_id: str, max_age: timedelta) -> None`
- `SessionTokens` returns an opaque cookie value and CSRF token; no database/session identifier is exposed directly.

- [ ] **Step 1: Add dependency and write failing security tests**

```python
def test_login_cookie_and_csrf_are_distinct(auth_service: AuthService) -> None:
    tokens = auth_service.login(SecretStr("correct horse battery staple"), "127.0.0.1", "test")
    assert tokens.cookie_token != tokens.csrf_token


def test_sensitive_action_requires_recent_totp(auth_service: AuthService) -> None:
    tokens = auth_service.login(SecretStr("correct horse battery staple"), "127.0.0.1", "test")
    with pytest.raises(RecentTotpRequired):
        auth_service.require_recent_totp(tokens.session_id, timedelta(minutes=5))
```

Add `pyotp>=2.9,<3` to runtime dependencies and regenerate `uv.lock` with `uv lock`.

- [ ] **Step 2: Verify security tests fail before implementation**

```powershell
$testBase = Join-Path $env:TEMP "pytest-goldguard-auth-red"
uv run pytest backend/tests/security/test_auth_service.py backend/tests/security/test_auth_dependencies.py -q -p no:cacheprovider --basetemp $testBase
```

- [ ] **Step 3: Implement hashed sessions and double-submit CSRF**

```python
@dataclass(frozen=True)
class SessionTokens:
    session_id: str
    cookie_token: str
    csrf_token: str
    expires_at: datetime


def require_mutation_auth(
    request: Request,
    session_cookie: Annotated[str | None, Cookie(alias="gg_session")] = None,
    csrf_header: Annotated[str | None, Header(alias="X-CSRF-Token")] = None,
) -> AuthPrincipal:
    return get_auth_service().authenticate_mutation(session_cookie, csrf_header, request)
```

Hash passwords with Argon2, store only hashed opaque session tokens, hash/compare CSRF tokens, enforce idle and absolute expiry, throttle login/TOTP failures, set `HttpOnly`, `Secure` in production, `SameSite=Strict`, and rotate sessions after successful TOTP.

- [ ] **Step 4: Run security and configuration checks**

```powershell
$testBase = Join-Path $env:TEMP "pytest-goldguard-auth-green"
uv run pytest backend/tests/security backend/tests/test_config.py -q -p no:cacheprovider --basetemp $testBase
uv run ruff check backend/goldguard/security backend/goldguard/web/auth_dependencies.py backend/tests/security
uv run mypy backend/goldguard/security backend/goldguard/web/auth_dependencies.py
```

- [ ] **Step 5: Commit**

```powershell
git add pyproject.toml uv.lock backend/goldguard/security backend/goldguard/web/auth_dependencies.py backend/tests/security
git commit -m "feat: secure admin sessions with totp and csrf"
```

### Task 4: Authenticated profile and authentication API

**Files:**
- Create: `backend/goldguard/web/schemas/__init__.py`
- Create: `backend/goldguard/web/routes/__init__.py`
- Create: `backend/goldguard/web/schemas/control.py`
- Create: `backend/goldguard/web/routes/auth.py`
- Create: `backend/goldguard/web/routes/settings.py`
- Modify: `backend/goldguard/web/app.py`
- Test: `backend/tests/web/test_auth_api.py`
- Test: `backend/tests/web/test_profile_api.py`

**Interfaces:**
- `POST /api/auth/login`, `POST /api/auth/totp`, `POST /api/auth/logout`, `GET /api/auth/session`.
- `GET /api/settings/profile`, `POST /api/settings/profile/preview`, `POST /api/settings/profile`.
- All response schemas expose decimal strings, selected scopes, calculated USDT equivalents, blockers, credential status, and timestamps.

- [ ] **Step 1: Write failing API authorization and atomicity tests**

```python
def test_settings_mutation_rejects_missing_csrf(client: TestClient) -> None:
    logged_in = login_without_totp(client)
    response = client.post("/api/settings/profile", json=valid_profile_payload())
    assert logged_in.status_code == 200
    assert response.status_code == 403


def test_profile_response_contains_usdt_equivalents_not_secrets(auth_client) -> None:
    response = auth_client.get("/api/settings/profile")
    assert response.status_code == 200
    body = response.json()
    assert body["equivalents"]["max_capital_per_trade_usdt"] == "50.00"
    assert "api_key" not in json.dumps(body).lower()
```

- [ ] **Step 2: Run focused API tests and confirm route failures**

```powershell
$testBase = Join-Path $env:TEMP "pytest-goldguard-control-api-red"
uv run pytest backend/tests/web/test_auth_api.py backend/tests/web/test_profile_api.py -q -p no:cacheprovider --basetemp $testBase
```

- [ ] **Step 3: Implement typed routers and compatibility responses**

```python
@router.post("/profile", response_model=ProfileResponse)
def activate_profile(
    payload: ProfileUpdate,
    principal: Annotated[AuthPrincipal, Depends(require_mutation_auth)],
) -> ProfileResponse:
    active = get_settings_service().activate(
        payload.to_domain(), principal.actor, principal.correlation_id, runtime_snapshot()
    )
    return ProfileResponse.from_active(active, account_equity_usdt())
```

Mount routers under `/api/auth` and `/api/settings`. Keep the old `GET /api/settings` response temporarily but mark it deprecated and derive it from the active profile so there is one owner.

- [ ] **Step 4: Run web and truthfulness tests**

```powershell
$testBase = Join-Path $env:TEMP "pytest-goldguard-control-api-green"
uv run pytest backend/tests/web/test_auth_api.py backend/tests/web/test_profile_api.py backend/tests/web/test_settings.py backend/tests/web/test_api_truthfulness.py -q -p no:cacheprovider --basetemp $testBase
uv run ruff check backend/goldguard/web backend/tests/web
uv run mypy backend/goldguard/web
```

- [ ] **Step 5: Commit**

```powershell
git add backend/goldguard/web/schemas/control.py backend/goldguard/web/routes/auth.py backend/goldguard/web/routes/settings.py backend/goldguard/web/app.py backend/tests/web/test_auth_api.py backend/tests/web/test_profile_api.py
git commit -m "feat: expose authenticated autonomous settings"
```

### Task 5: Persisted Live arming and control-plane preflight

**Files:**
- Create: `backend/goldguard/live/__init__.py`
- Create: `backend/goldguard/live/models.py`
- Create: `backend/goldguard/live/arming.py`
- Create: `backend/goldguard/services/preflight.py`
- Create: `backend/goldguard/web/routes/control.py`
- Modify: `backend/goldguard/risk/state_machine.py`
- Test: `backend/tests/live/test_arming.py`
- Test: `backend/tests/services/test_preflight.py`
- Test: `backend/tests/web/test_control_api.py`

**Interfaces:**
- `PreflightService.evaluate(profile: AutonomousProfile) -> PreflightReport`
- `ArmingService.arm(request: ArmRequest, principal: AuthPrincipal, report: PreflightReport) -> ArmingState`
- `ArmingService.on_restart() -> ArmingState` always returns `armed_pending_reconciliation` for a persisted armed profile.
- Routes: `GET /api/preflight`, `POST /api/live/arm`, `POST /api/live/disarm`, `POST /api/control/pause`, `POST /api/control/cancel-all`, `POST /api/control/close-all`.

- [ ] **Step 1: Write failing independent-gate tests**

```python
@pytest.mark.parametrize("failed_gate", [
    "paper_qualification", "binance_permissions", "withdrawals_disabled",
    "market_freshness", "database_integrity", "opencodex_route",
    "hermes_route", "telegram_critical", "reconciliation",
])
def test_live_arm_rejects_each_failed_gate(arming_service, passing_report, failed_gate) -> None:
    report = passing_report.with_failure(failed_gate)
    with pytest.raises(LiveArmingRejected, match=failed_gate):
        arming_service.arm(valid_arm_request(), recent_totp_principal(), report)


def test_restart_preserves_intent_but_blocks_entries_until_reconciled(armed_service) -> None:
    state = armed_service.on_restart()
    assert state.status == ArmingStatus.ARMED_PENDING_RECONCILIATION
    assert state.new_entries_allowed is False
```

- [ ] **Step 2: Run failures**

```powershell
$testBase = Join-Path $env:TEMP "pytest-goldguard-arming-red"
uv run pytest backend/tests/live/test_arming.py backend/tests/services/test_preflight.py backend/tests/web/test_control_api.py -q -p no:cacheprovider --basetemp $testBase
```

- [ ] **Step 3: Implement persisted arming state and typed confirmation**

```python
class ArmRequest(BaseModel):
    confirmation: str
    profile_version: str
    expected_equity_usdt: Decimal


def expected_confirmation(profile: AutonomousProfile) -> str:
    products = "+".join(profile.enabled_product_labels())
    return f"ARM LIVE {products} MAX {profile.risk.max_capital_per_trade_rate:%}"
```

Arming requires exact profile version/equity snapshot, recent TOTP, passing preflight, and append-only audit. Cancel/Close routes operate only on application-owned orders/positions and remain abstract until execution services are supplied by later plans.

- [ ] **Step 4: Run live/control/state-machine suites**

```powershell
$testBase = Join-Path $env:TEMP "pytest-goldguard-arming-green"
uv run pytest backend/tests/live backend/tests/services/test_preflight.py backend/tests/web/test_control_api.py backend/tests/risk/test_state_machine.py -q -p no:cacheprovider --basetemp $testBase
uv run ruff check backend/goldguard/live backend/goldguard/services/preflight.py backend/goldguard/web/routes/control.py backend/tests/live
uv run mypy backend/goldguard/live backend/goldguard/services/preflight.py backend/goldguard/web/routes/control.py
```

- [ ] **Step 5: Commit**

```powershell
git add backend/goldguard/live backend/goldguard/services/preflight.py backend/goldguard/web/routes/control.py backend/goldguard/risk/state_machine.py backend/tests/live backend/tests/services/test_preflight.py backend/tests/web/test_control_api.py
git commit -m "feat: gate and persist live arming"
```

### Task 6: Restrictive CORS and OpenCodex-only provider credentials

**Files:**
- Modify: `backend/goldguard/config.py`
- Modify: `backend/goldguard/web/app.py`
- Modify: `backend/goldguard/providers/service.py`
- Modify: `.env.example`
- Modify: `docker-compose.prod.yml`
- Test: `backend/tests/security/test_boundaries.py`
- Test: `backend/tests/providers/test_service.py`

**Interfaces:**
- `Settings.cors_origins: tuple[str, ...]` requires explicit HTTPS origins in production.
- GoldGuard retains only `OPENCODEX_BASE_URL`, data-plane token, and optional management token; direct Gemini/Antigravity/OpenRouter provider keys are rejected/ignored by the trading core.
- Provider status responses expose only status/fingerprint metadata returned by OpenCodex.

- [ ] **Step 1: Write failing production-boundary tests**

```python
def test_production_rejects_wildcard_cors(monkeypatch) -> None:
    monkeypatch.setenv("GOLDGUARD_ENVIRONMENT", "production")
    monkeypatch.setenv("GOLDGUARD_CORS_ORIGINS", "*")
    with pytest.raises(ValidationError, match="wildcard"):
        Settings()


def test_core_has_no_direct_antigravity_key_field() -> None:
    fields = Settings.model_fields
    assert "gemini_api_key" not in fields
    assert "openrouter_api_key" not in fields
```

- [ ] **Step 2: Verify boundary failures**

```powershell
$testBase = Join-Path $env:TEMP "pytest-goldguard-boundary-red"
uv run pytest backend/tests/security/test_boundaries.py backend/tests/providers/test_service.py backend/tests/test_config.py -q -p no:cacheprovider --basetemp $testBase
```

- [ ] **Step 3: Remove direct provider-key ownership and constrain middleware**

```python
app.add_middleware(
    CORSMiddleware,
    allow_origins=list(settings.cors_origins),
    allow_credentials=True,
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type", "X-CSRF-Token"],
)
```

Remove direct provider key injection from startup and Compose. Update `.env.example` to distinguish OpenCodex service authentication from provider authentication stored inside OpenCodex.

- [ ] **Step 4: Run Gate 1 verification**

```powershell
$testBase = Join-Path $env:TEMP "pytest-goldguard-gate1"
uv run pytest backend/tests/domain backend/tests/storage backend/tests/security backend/tests/live backend/tests/providers backend/tests/services/test_settings_service.py backend/tests/services/test_preflight.py backend/tests/web -q -p no:cacheprovider --basetemp $testBase
uv run ruff check backend
uv run mypy backend/goldguard
git diff --check
```

- [ ] **Step 5: Commit**

```powershell
git add backend/goldguard/config.py backend/goldguard/web/app.py backend/goldguard/providers/service.py .env.example docker-compose.prod.yml backend/tests/security/test_boundaries.py backend/tests/providers/test_service.py backend/tests/test_config.py
git commit -m "security: isolate provider auth behind opencodex"
```
