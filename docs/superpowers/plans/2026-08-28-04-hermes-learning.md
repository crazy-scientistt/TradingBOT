# Hermes Learning and OpenCodex Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the prebuilt Hermes Agent the real persistent researcher/learner, powered by the selected Antigravity model through OpenCodex, with trade reflections, structured memory, bounded genomes, autonomous qualification, background promotion, rollback, and quarantine.

**Architecture:** Run the official `nousresearch/hermes-agent` gateway as a separate private service with its own `/opt/data` volume and API key. GoldGuard exposes a sanitized, quota-bound research bridge; Hermes never receives secrets, broker access, arbitrary code execution, settings mutation, or sealed-holdout data.

**Tech Stack:** Official NousResearch Hermes Agent Docker image, OpenCodex 2.33.0 initially, Antigravity provider auth, Python 3.12 bridge/services, SQLite/WAL, FastAPI, pytest, Docker Compose.

**Spec:** `docs/superpowers/specs/2026-08-28-autonomous-hermes-trading-platform-design.md`

## Global Constraints

- Reuse the prebuilt Hermes Agent; do not rebuild a competing general agent framework.
- OpenCodex exclusively owns Antigravity provider credentials and model routing.
- GoldGuard/Hermes exchange sanitized typed packets over private authenticated APIs.
- Candidate strategies are declarative data only; no eval, source code, shell, or arbitrary file paths.
- Paper/Live memories retain explicit mode/product/pair tags.
- A losing trade is not automatically a mistake; a winning trade is not automatically sound.
- Promotion/rollback is deterministic and independent of UI/API reads.

---

### Task 1: Official Hermes gateway as an isolated local service

**Files:**
- Create: `hermes/Dockerfile`
- Create: `hermes/healthcheck.sh`
- Modify: `hermes/config.yaml`
- Modify: `hermes/SOUL.md`
- Modify: `docker-compose.autonomous.yml`
- Modify: `.env.example`
- Test: `backend/tests/e2e/test_hermes_container_contract.py`

**Interfaces:**
- Image source: `nousresearch/hermes-agent:latest` for local integration; Gate 8 records and pins the verified repository digest for release.
- Command: `gateway run`; private API port `8642`; volume `/opt/data`.
- Required environment: `API_SERVER_ENABLED=true`, `API_SERVER_HOST=0.0.0.0`, `API_SERVER_KEY`, OpenCodex base URL/token/model route.

- [ ] **Step 1: Write failing Compose/container-contract tests**

```python
def test_compose_has_private_hermes_gateway(compose_config: dict) -> None:
    service = compose_config["services"]["hermes"]
    assert service["image"] == "nousresearch/hermes-agent:latest"
    assert service["command"] == ["gateway", "run"]
    assert service["volumes"] == ["hermes-data:/opt/data"]
    assert "ports" not in service
    assert service["environment"]["API_SERVER_HOST"] == "0.0.0.0"
```

- [ ] **Step 2: Verify missing service fails**

```powershell
$testBase = Join-Path $env:TEMP "pytest-goldguard-hermes-container-red"
uv run pytest backend/tests/e2e/test_hermes_container_contract.py -q -p no:cacheprovider --basetemp $testBase
```

- [ ] **Step 3: Add the official gateway and constrained identity**

```yaml
hermes:
  image: nousresearch/hermes-agent:latest
  command: ["gateway", "run"]
  restart: unless-stopped
  environment:
    API_SERVER_ENABLED: "true"
    API_SERVER_HOST: "0.0.0.0"
    API_SERVER_KEY: ${HERMES_BRIDGE_TOKEN}
    OPENCODEX_BASE_URL: http://opencodex:10100/v1
    OPENCODEX_API_AUTH_TOKEN: ${OPENCODEX_API_AUTH_TOKEN}
  volumes:
    - hermes-data:/opt/data
  networks:
    - goldguard-net
```

The Dockerfile extends the official image only to copy the approved GoldGuard skill/config/SOUL files with correct ownership; it does not install broker clients or mount the repository/backend data.

- [ ] **Step 4: Validate Compose and contract**

```powershell
docker compose -f docker-compose.autonomous.yml --env-file .env.autonomous config
$testBase = Join-Path $env:TEMP "pytest-goldguard-hermes-container-green"
uv run pytest backend/tests/e2e/test_hermes_container_contract.py -q -p no:cacheprovider --basetemp $testBase
```

- [ ] **Step 5: Commit**

```powershell
git add hermes docker-compose.autonomous.yml .env.example backend/tests/e2e/test_hermes_container_contract.py
git commit -m "ops: run isolated prebuilt hermes agent"
```

### Task 2: Sanitized Hermes research tool surface

**Files:**
- Create: `backend/goldguard/hermes/tools.py`
- Create: `backend/goldguard/web/routes/hermes_bridge.py`
- Modify: `backend/goldguard/hermes/models.py`
- Modify: `backend/goldguard/hermes/client.py`
- Test: `backend/tests/hermes/test_tools.py`
- Modify: `backend/tests/hermes/test_isolation.py`

**Interfaces:**
- Read-only tools: `get_candles`, `get_features`, `get_evidence`, `get_trade_outcomes`, `get_lessons`, `run_backtest`, `get_evaluation`.
- Sole write tool: `submit_genome(genome_json) -> GenomeSubmissionResult`.
- Every call uses bearer auth, byte/query/time quotas, audit events, and typed error responses.

- [ ] **Step 1: Write failing isolation/quota tests**

```python
@pytest.mark.parametrize("forbidden", ["broker", "secret", "settings", "shell", "holdout"])
def test_bridge_exposes_no_forbidden_tool(tool_registry, forbidden) -> None:
    assert all(forbidden not in name.lower() for name in tool_registry.names())


def test_holdout_query_is_always_rejected(client) -> None:
    response = client.post("/internal/hermes/tools/get_evaluation", json={"partition": "holdout"})
    assert response.status_code == 403
    assert response.json()["code"] == "SEALED_HOLDOUT"
```

- [ ] **Step 2: Verify failures**

```powershell
$testBase = Join-Path $env:TEMP "pytest-goldguard-hermes-tools-red"
uv run pytest backend/tests/hermes/test_tools.py backend/tests/hermes/test_isolation.py -q -p no:cacheprovider --basetemp $testBase
```

- [ ] **Step 3: Implement allowlisted typed dispatch**

```python
class HermesToolRegistry:
    async def call(self, name: str, payload: dict[str, object], principal: HermesPrincipal) -> ToolResult:
        handler = self._handlers.get(name)
        if handler is None:
            raise UnknownHermesTool(name)
        self._quota.consume(principal, name, canonical_size(payload))
        return await handler(payload)
```

Responses exclude credentials, internal file paths, unsealed holdout, raw prompts, and unrestricted query parameters. Invalid genome responses include actionable schema/bound errors without executing anything.

- [ ] **Step 4: Run Hermes isolation suite**

```powershell
$testBase = Join-Path $env:TEMP "pytest-goldguard-hermes-tools-green"
uv run pytest backend/tests/hermes/test_tools.py backend/tests/hermes/test_isolation.py -q -p no:cacheprovider --basetemp $testBase
uv run ruff check backend/goldguard/hermes backend/goldguard/web/routes/hermes_bridge.py backend/tests/hermes
uv run mypy backend/goldguard/hermes backend/goldguard/web/routes/hermes_bridge.py
```

- [ ] **Step 5: Commit**

```powershell
git add backend/goldguard/hermes backend/goldguard/web/routes/hermes_bridge.py backend/tests/hermes/test_tools.py backend/tests/hermes/test_isolation.py
git commit -m "feat: expose bounded hermes research tools"
```

### Task 3: Route every Hermes/context/decision call through selected OpenCodex models

**Files:**
- Modify: `backend/goldguard/hermes/generator.py`
- Modify: `backend/goldguard/hermes/service.py`
- Modify: `backend/goldguard/context/sources.py`
- Modify: `backend/goldguard/ai/decision.py`
- Modify: `backend/goldguard/providers/service.py`
- Modify: `backend/goldguard/web/app.py`
- Test: `backend/tests/hermes/test_routing.py`
- Modify: `backend/tests/providers/test_service.py`
- Modify: `backend/tests/ai/test_decision.py`

**Interfaces:**
- `RouteService.require(role: Literal['decision','context','hermes']) -> ModelRoute`.
- All production callers accept `ModelRoute` at call time; no default Antigravity model remains in a worker constructor.
- Route changes while Live-armed move arming to pending reconciliation and block new entries until the route health probe passes.

- [ ] **Step 1: Write failing no-hardcoded-route tests**

```python
async def test_hermes_uses_active_route(route_service, generator) -> None:
    route_service.set_route("hermes", "opencodex", "google-antigravity/gemini-3.1-pro")
    await generator.propose(packet())
    assert generator.gateway.last_request["model"] == "google-antigravity/gemini-3.1-pro"


def test_route_change_disarms_ready_entries(live_system) -> None:
    live_system.routes.set_route("decision", "opencodex", "google-antigravity/gemini-3.7-flash")
    assert live_system.arming.new_entries_allowed is False
```

- [ ] **Step 2: Confirm current defaults fail**

```powershell
$testBase = Join-Path $env:TEMP "pytest-goldguard-hermes-routing-red"
uv run pytest backend/tests/hermes/test_routing.py backend/tests/providers/test_service.py backend/tests/ai/test_decision.py -q -p no:cacheprovider --basetemp $testBase
```

- [ ] **Step 3: Inject route service into all callers**

```python
route = self._routes.require("hermes")
response = await self._gateway.chat_completion(
    model=route.model,
    messages=messages,
    response_format=response_schema,
)
```

Model catalog, health, quota, provider-auth persistence, and test-connection status come only from OpenCodex.

- [ ] **Step 4: Run AI/provider/Hermes/context suites**

```powershell
$testBase = Join-Path $env:TEMP "pytest-goldguard-hermes-routing-green"
uv run pytest backend/tests/ai backend/tests/providers backend/tests/hermes backend/tests/context -q -p no:cacheprovider --basetemp $testBase
uv run ruff check backend/goldguard/ai backend/goldguard/providers backend/goldguard/hermes backend/goldguard/context
uv run mypy backend/goldguard/ai backend/goldguard/providers backend/goldguard/hermes backend/goldguard/context
```

- [ ] **Step 5: Commit**

```powershell
git add backend/goldguard/ai backend/goldguard/providers backend/goldguard/hermes backend/goldguard/context backend/goldguard/web/app.py backend/tests/ai backend/tests/providers backend/tests/hermes/test_routing.py
git commit -m "fix: honor opencodex model routes everywhere"
```

### Task 4: Outcome attribution, reflections, and reusable memory

**Files:**
- Create: `backend/goldguard/memory/outcomes.py`
- Create: `backend/goldguard/memory/lessons.py`
- Create: `backend/goldguard/storage/migrations/006_learning.sql`
- Modify: `backend/goldguard/memory/reflections.py`
- Modify: `backend/goldguard/memory/engine.py`
- Modify: `backend/goldguard/services/runtime_supervisor.py`
- Test: `backend/tests/memory/test_outcomes.py`
- Test: `backend/tests/memory/test_lessons.py`
- Modify: `backend/tests/memory/test_reflections.py`

**Interfaces:**
- `OutcomeAttributor.attribute(learning_record) -> OutcomeAttribution`.
- Categories: hypothesis, timing, regime, evidence, sizing proposal, execution, protection, data/system, normal variance.
- `LessonEngine.derive(reflections) -> tuple[Lesson, ...]` returns bounded diverse lessons with mode/product/pair/regime tags.

- [ ] **Step 1: Write failing loss-is-not-always-mistake tests**

```python
def test_rule_followed_loss_is_normal_variance(attributor) -> None:
    result = attributor.attribute(compliant_trade(net_pnl="-1.25", positive_expected_edge=True))
    assert result.primary_category == OutcomeCategory.NORMAL_VARIANCE


def test_winning_rule_violation_is_not_positive_lesson(attributor) -> None:
    result = attributor.attribute(noncompliant_trade(net_pnl="5.00"))
    assert result.decision_quality == DecisionQuality.INVALID
```

- [ ] **Step 2: Verify missing attribution fails**

```powershell
$testBase = Join-Path $env:TEMP "pytest-goldguard-learning-records-red"
uv run pytest backend/tests/memory/test_outcomes.py backend/tests/memory/test_lessons.py backend/tests/memory/test_reflections.py -q -p no:cacheprovider --basetemp $testBase
```

- [ ] **Step 3: Persist complete immutable learning records**

```python
@dataclass(frozen=True)
class OutcomeAttribution:
    primary_category: OutcomeCategory
    secondary_categories: tuple[OutcomeCategory, ...]
    decision_quality: DecisionQuality
    confidence: Decimal
    evidence_codes: tuple[str, ...]
```

Closed trades and material HOLD/rejection decisions store features, evidence, intended/actual execution, cost path, protection/reconciliation events, strategy/model versions, and health. The runtime calls memory directly after durable close/rejection; no UI trigger is involved.

- [ ] **Step 4: Run memory/runtime suites**

```powershell
$testBase = Join-Path $env:TEMP "pytest-goldguard-learning-records-green"
uv run pytest backend/tests/memory backend/tests/services/test_runtime_supervisor.py backend/tests/storage -q -p no:cacheprovider --basetemp $testBase
uv run ruff check backend/goldguard/memory backend/tests/memory
uv run mypy backend/goldguard/memory
```

- [ ] **Step 5: Commit**

```powershell
git add backend/goldguard/memory backend/goldguard/storage/migrations/006_learning.sql backend/goldguard/services/runtime_supervisor.py backend/tests/memory
git commit -m "feat: learn from cost-adjusted outcomes"
```

### Task 5: Candidate evaluation and sealed qualification pipeline

**Files:**
- Create: `backend/goldguard/research/__init__.py`
- Create: `backend/goldguard/storage/migrations/007_qualification.sql`
- Modify: `backend/goldguard/strategy/genome.py`
- Modify: `backend/goldguard/backtest/engine.py`
- Modify: `backend/goldguard/backtest/walk_forward.py`
- Create: `backend/goldguard/research/qualification.py`
- Modify: `backend/goldguard/services/promotion_controller.py`
- Test: `backend/tests/research/test_qualification.py`
- Modify: `backend/tests/strategy/test_genome.py`
- Modify: `backend/tests/backtest/test_walk_forward.py`
- Modify: `backend/tests/services/test_promotion_controller.py`

**Interfaces:**
- `QualificationService.evaluate_candidate(genome_id) -> QualificationReport`.
- States: candidate, development_passed, validation_passed, holdout_passed, shadow, qualified, canary, active, quarantined, retired.
- Sealed holdout becomes readable only to the deterministic evaluator after a candidate freeze record.

- [ ] **Step 1: Write failing gate-order and threshold tests**

```python
def test_candidate_cannot_skip_validation(pipeline) -> None:
    with pytest.raises(InvalidGenomeTransition):
        pipeline.transition("candidate-1", GenomeStage.HOLDOUT_PASSED)


def test_first_live_requires_full_paper_floor(qualification) -> None:
    report = qualification.evaluate(first_live_evidence(trades=199, days=14, regimes=2))
    assert report.qualified is False
    assert "MIN_200_PAPER_TRADES" in report.failures
```

- [ ] **Step 2: Verify existing weak gates fail**

```powershell
$testBase = Join-Path $env:TEMP "pytest-goldguard-qualification-red"
uv run pytest backend/tests/research/test_qualification.py backend/tests/strategy/test_genome.py backend/tests/backtest/test_walk_forward.py backend/tests/services/test_promotion_controller.py -q -p no:cacheprovider --basetemp $testBase
```

- [ ] **Step 3: Implement cost-adjusted statistical gates**

```python
@dataclass(frozen=True)
class QualificationReport:
    genome_id: str
    qualified: bool
    stage: GenomeStage
    net_expectancy: Decimal
    expectancy_ci95_lower: Decimal
    trade_count: int
    elapsed_days: int
    regimes: tuple[str, ...]
    failures: tuple[str, ...]
```

`007_qualification.sql` migrates existing genome status values into the approved transition set without losing payloads/evaluations. Backtest gates use development, purged walk-forward validation, one-time sealed holdout, realistic costs, and immutable run hashes. First-Live floor is 200 trades/14 days/two regimes/positive 95% lower bound; later strategies require 100 shadow trades/seven days/two regimes plus all historical gates.

- [ ] **Step 4: Run strategy/backtest/research suites**

```powershell
$testBase = Join-Path $env:TEMP "pytest-goldguard-qualification-green"
uv run pytest backend/tests/strategy backend/tests/backtest backend/tests/research backend/tests/services/test_promotion_controller.py -q -p no:cacheprovider --basetemp $testBase
uv run ruff check backend/goldguard/strategy backend/goldguard/backtest backend/goldguard/research backend/tests/research
uv run mypy backend/goldguard/strategy backend/goldguard/backtest backend/goldguard/research
```

- [ ] **Step 5: Commit**

```powershell
git add backend/goldguard/storage/migrations/007_qualification.sql backend/goldguard/strategy backend/goldguard/backtest backend/goldguard/research backend/goldguard/services/promotion_controller.py backend/tests/strategy backend/tests/backtest backend/tests/research backend/tests/services/test_promotion_controller.py
git commit -m "feat: qualify hermes strategies statistically"
```

### Task 6: Background Hermes loop, promotion, rollback, and quarantine

**Files:**
- Create: `backend/goldguard/services/hermes_supervisor.py`
- Create: `backend/goldguard/services/promotion_supervisor.py`
- Modify: `backend/goldguard/hermes/loop.py`
- Modify: `backend/goldguard/services/runtime_supervisor.py`
- Modify: `backend/goldguard/web/app.py`
- Test: `backend/tests/services/test_hermes_supervisor.py`
- Test: `backend/tests/services/test_promotion_supervisor.py`
- Test: `backend/tests/e2e/test_hermes_learning_cycle.py`

**Interfaces:**
- `HermesSupervisor.start/stop/status/trigger_due` schedules bounded research and persists iteration/quota state across restart.
- `PromotionSupervisor.observe()` runs without API/UI polling, advances qualified candidates, and restores a byte-identical safe parent on rollback.
- Live-disabled qualification remains Paper; Live-armed qualification creates only a smallest-risk canary eligibility record for Gate 5 execution.

- [ ] **Step 1: Write failing unattended-loop tests**

```python
async def test_rollback_occurs_without_dashboard_polling(system) -> None:
    await system.promote_canary("candidate-1")
    await system.record_canary_breach("candidate-1", "DRAWDOWN")
    await system.promotion_supervisor.tick()
    assert system.active_genome_hash() == system.baseline_genome_hash()
    assert system.genome_stage("candidate-1") == GenomeStage.QUARANTINED


async def test_iteration_quota_survives_restart(system) -> None:
    await system.hermes_supervisor.consume_all_daily_iterations()
    restarted = await system.restart()
    assert (await restarted.hermes_supervisor.tick()).code == "QUOTA_EXHAUSTED"
```

- [ ] **Step 2: Verify current API-driven behavior fails**

```powershell
$testBase = Join-Path $env:TEMP "pytest-goldguard-hermes-supervisors-red"
uv run pytest backend/tests/services/test_hermes_supervisor.py backend/tests/services/test_promotion_supervisor.py backend/tests/e2e/test_hermes_learning_cycle.py -q -p no:cacheprovider --basetemp $testBase
```

- [ ] **Step 3: Install explicit background ownership**

```python
async def promotion_loop(supervisor: PromotionSupervisor, stop: asyncio.Event) -> None:
    while not stop.is_set():
        await supervisor.observe()
        try:
            await asyncio.wait_for(stop.wait(), timeout=5.0)
        except TimeoutError:
            continue
```

Remove `_observe_canary()` side effects from read endpoints. Reads report durable state only. Autopromotion settings authoritatively start/stop candidate advancement while existing active strategy safety monitoring always continues.

- [ ] **Step 4: Run Gate 4 verification and actual local route smoke**

```powershell
$testBase = Join-Path $env:TEMP "pytest-goldguard-gate4"
uv run pytest backend/tests/hermes backend/tests/memory backend/tests/strategy backend/tests/backtest backend/tests/research backend/tests/services/test_hermes_supervisor.py backend/tests/services/test_promotion_supervisor.py backend/tests/e2e/test_hermes_learning_cycle.py -q -p no:cacheprovider --basetemp $testBase
uv run ruff check backend
uv run mypy backend/goldguard
docker compose -f docker-compose.autonomous.yml --env-file .env.autonomous config
docker compose -f docker-compose.autonomous.yml --env-file .env.autonomous up -d opencodex hermes backend
docker compose -f docker-compose.autonomous.yml --env-file .env.autonomous ps
```

Expected: automated checks exit `0`; services become healthy; a diagnostic request records `hermes` route/model/provider as returned by OpenCodex. Do not print credentials.

- [ ] **Step 5: Commit**

```powershell
git add backend/goldguard/services/hermes_supervisor.py backend/goldguard/services/promotion_supervisor.py backend/goldguard/hermes/loop.py backend/goldguard/services/runtime_supervisor.py backend/goldguard/web/app.py backend/tests/services/test_hermes_supervisor.py backend/tests/services/test_promotion_supervisor.py backend/tests/e2e/test_hermes_learning_cycle.py
git commit -m "feat: run autonomous hermes learning safely"
```
