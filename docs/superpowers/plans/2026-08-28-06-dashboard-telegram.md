# Dashboard and Telegram Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Deliver a truthful, responsive Binance-style autonomous dashboard with persisted settings, orders, positions/holdings, P&L, research, learning, diagnostics, emergency controls, and configurable Telegram notifications.

**Architecture:** Add typed read-model services and schema-first FastAPI routers; the React client consumes one snapshot plus bounded incremental streams. UI components render explicit Paper/Live, loading/empty/stale/degraded/error states and never synthesize business data.

**Tech Stack:** FastAPI, Pydantic 2, React 19, TypeScript 5.9, Vite 7, Vitest, Testing Library, lightweight-charts, Recharts, Telegram Bot HTTP API via httpx, Playwright.

**Spec:** `docs/superpowers/specs/2026-08-28-autonomous-hermes-trading-platform-design.md`

## Global Constraints

- Every displayed value has backend provenance or is explicitly unavailable/stale.
- Paper/Live appears on every order, position, trade, P&L, strategy evidence, and report.
- No seeded/mock/fallback production data.
- Settings show percentages and live USDT equivalents; leverage appears only for Futures.
- Disabling a scope blocks new entries but does not abandon positions.
- Telegram token remains server-side; frontend sees destination/status/preferences only.
- Critical Telegram categories cannot be muted while Telegram is enabled.

---

### Task 1: Typed dashboard read models and route decomposition

**Files:**
- Create: `backend/goldguard/readmodels/__init__.py`
- Create: `backend/goldguard/readmodels/dashboard.py`
- Create: `backend/goldguard/web/schemas/dashboard.py`
- Create: `backend/goldguard/web/routes/dashboard.py`
- Create: `backend/goldguard/web/routes/execution.py`
- Modify: `backend/goldguard/web/app.py`
- Test: `backend/tests/readmodels/test_dashboard.py`
- Test: `backend/tests/web/test_execution_api.py`
- Modify: `backend/tests/web/test_api_truthfulness.py`

**Interfaces:**
- `DashboardReadModel.snapshot(now) -> DashboardSnapshot`.
- Routes: `/api/dashboard`, `/api/orders`, `/api/positions`, `/api/holdings`, `/api/trades`, `/api/pnl`, `/api/diagnostics`.
- Each section is `available|degraded|unavailable`, with source, observed time, data, and detail.

- [ ] **Step 1: Write failing no-fabrication and cost-P&L tests**

```python
def test_empty_orders_are_truthful_empty_not_seeded(client) -> None:
    body = client.get("/api/orders").json()
    assert body["availability"] == "available"
    assert body["data"] == []


def test_position_net_pnl_reconciles_costs(client, seeded_position) -> None:
    position = client.get("/api/positions").json()["data"][0]
    assert Decimal(position["net_pnl_usdt"]) == (
        Decimal(position["gross_pnl_usdt"])
        - Decimal(position["fees_usdt"])
        - Decimal(position["funding_usdt"])
        - Decimal(position["slippage_usdt"])
    )
```

- [ ] **Step 2: Verify route/read-model failures**

```powershell
$testBase = Join-Path $env:TEMP "pytest-goldguard-readmodels-red"
uv run pytest backend/tests/readmodels/test_dashboard.py backend/tests/web/test_execution_api.py backend/tests/web/test_api_truthfulness.py -q -p no:cacheprovider --basetemp $testBase
```

- [ ] **Step 3: Implement backend-owned read models**

```python
class AvailabilityEnvelope(BaseModel, Generic[T]):
    availability: Availability
    data: T | None
    source: str
    observed_at: datetime
    detail: str | None = None
```

Read models join durable orders/fills/positions/protection/equity/evidence/strategy/health records and never mutate state. Existing endpoints delegate to the same owner until frontend migration is complete.

- [ ] **Step 4: Run web/read-model checks**

```powershell
$testBase = Join-Path $env:TEMP "pytest-goldguard-readmodels-green"
uv run pytest backend/tests/readmodels backend/tests/web -q -p no:cacheprovider --basetemp $testBase
uv run ruff check backend/goldguard/readmodels backend/goldguard/web backend/tests/readmodels
uv run mypy backend/goldguard/readmodels backend/goldguard/web
```

- [ ] **Step 5: Commit**

```powershell
git add backend/goldguard/readmodels backend/goldguard/web/schemas/dashboard.py backend/goldguard/web/routes/dashboard.py backend/goldguard/web/routes/execution.py backend/goldguard/web/app.py backend/tests/readmodels backend/tests/web/test_execution_api.py backend/tests/web/test_api_truthfulness.py
git commit -m "feat: expose truthful trading read models"
```

### Task 2: Frontend API types, authentication shell, and autonomous Settings

**Files:**
- Modify: `frontend/src/api/client.ts`
- Modify: `frontend/src/types/dashboard.ts`
- Modify: `frontend/src/types/index.ts`
- Modify: `frontend/src/context/BotContext.tsx`
- Create: `frontend/src/components/auth/LoginPanel.tsx`
- Create: `frontend/src/components/settings/AutonomousSettings.tsx`
- Modify: `frontend/src/components/views/SettingsModal.tsx`
- Test: `frontend/src/tests/components/LoginPanel.test.tsx`
- Test: `frontend/src/tests/components/AutonomousSettings.test.tsx`

**Interfaces:**
- Client stores no session secret; cookie is HttpOnly and mutation calls send the in-memory CSRF token.
- `AutonomousProfileView` mirrors backend strings/enums.
- Settings submit preview first, show blockers/equivalents, then activate with explicit confirmation.

- [ ] **Step 1: Write failing login/settings tests**

```tsx
it('shows USDT equivalents beneath percentage ceilings', async () => {
  render(<AutonomousSettings />);
  expect(await screen.findByText('50.00 USDT maximum for one trade')).toBeInTheDocument();
  expect(screen.getByText('2,000.00 USDT maximum total exposure')).toBeInTheDocument();
});

it('hides leverage when futures is disabled', async () => {
  render(<AutonomousSettings initialProfile={spotOnlyProfile} />);
  expect(screen.queryByLabelText('Max Futures Leverage')).not.toBeInTheDocument();
});
```

- [ ] **Step 2: Verify frontend tests fail**

```powershell
npm --prefix frontend test -- LoginPanel.test.tsx AutonomousSettings.test.tsx
```

- [ ] **Step 3: Implement typed client and user-friendly Settings flow**

```ts
export interface RiskCeilingsView {
  max_capital_per_trade_rate: string;
  max_futures_leverage: number;
  max_total_exposure_rate: string;
  rolling_24h_loss_limit_rate: string;
}

export interface RiskEquivalentsView {
  max_capital_per_trade_usdt: string;
  max_total_exposure_usdt: string;
  rolling_24h_loss_limit_usdt: string;
}
```

Use Binance-familiar labels: Paper/Live, Spot, USD-M Futures, pair selectors, Max Capital per Trade, Max Futures Leverage, Max Total Exposure, Rolling 24-Hour Loss Limit. Explain that AI selects actual values below ceilings.

- [ ] **Step 4: Run focused frontend checks**

```powershell
npm --prefix frontend test -- LoginPanel.test.tsx AutonomousSettings.test.tsx
npm --prefix frontend run typecheck
npm --prefix frontend run build
```

- [ ] **Step 5: Commit**

```powershell
git add frontend/src/api/client.ts frontend/src/types frontend/src/context/BotContext.tsx frontend/src/components/auth/LoginPanel.tsx frontend/src/components/settings/AutonomousSettings.tsx frontend/src/components/views/SettingsModal.tsx frontend/src/tests/components/LoginPanel.test.tsx frontend/src/tests/components/AutonomousSettings.test.tsx
git commit -m "feat: configure autonomous trading in app"
```

### Task 3: Orders, positions/holdings, trade history, and emergency controls

**Files:**
- Create: `frontend/src/components/views/OrdersView.tsx`
- Create: `frontend/src/components/views/PositionsView.tsx`
- Modify: `frontend/src/components/views/TradesView.tsx`
- Modify: `frontend/src/components/risk/EmergencyCockpit.tsx`
- Modify: `frontend/src/App.tsx`
- Test: `frontend/src/tests/components/OrdersView.test.tsx`
- Test: `frontend/src/tests/components/PositionsView.test.tsx`
- Modify: `frontend/src/tests/components/BotControls.test.tsx`

**Interfaces:**
- Order row: mode/product/pair/side/type/quantity/filled/remaining/price/status/protection/age.
- Position row: entry/average/mark/margin/leverage/liquidation estimate/TP/SL/duration/gross/net/fees/funding/slippage.
- Cancel All and Close All show scope summary, typed confirmation, and TOTP challenge before mutation.

- [ ] **Step 1: Write failing rendering and emergency-flow tests**

```tsx
it('renders futures leverage, liquidation and cost-adjusted pnl', async () => {
  render(<PositionsView />);
  expect(await screen.findByText('4x isolated')).toBeInTheDocument();
  expect(screen.getByText('Liquidation 52,100.00')).toBeInTheDocument();
  expect(screen.getByText('Net P&L +3.42 USDT')).toBeInTheDocument();
});

it('requires confirmation and totp before close all', async () => {
  render(<EmergencyCockpit />);
  await userEvent.click(screen.getByRole('button', { name: 'Close All' }));
  expect(screen.getByLabelText('Confirmation phrase')).toBeRequired();
  expect(screen.getByLabelText('2FA code')).toBeRequired();
});
```

- [ ] **Step 2: Verify tests fail**

```powershell
npm --prefix frontend test -- OrdersView.test.tsx PositionsView.test.tsx BotControls.test.tsx
```

- [ ] **Step 3: Implement truthful tables/cards and protected actions**

```tsx
const pnl = position.net_pnl_usdt === null
  ? <Unavailable label="Net P&L" />
  : <Money value={position.net_pnl_usdt} currency="USDT" />;
```

Position/product OFF controls call profile preview/activation and show “new entries blocked; existing position remains managed.” Never infer Live from frontend state.

- [ ] **Step 4: Run focused and existing component tests**

```powershell
npm --prefix frontend test
npm --prefix frontend run typecheck
npm --prefix frontend run build
```

- [ ] **Step 5: Commit**

```powershell
git add frontend/src/components/views/OrdersView.tsx frontend/src/components/views/PositionsView.tsx frontend/src/components/views/TradesView.tsx frontend/src/components/risk/EmergencyCockpit.tsx frontend/src/App.tsx frontend/src/tests/components
git commit -m "feat: show and control active trading truthfully"
```

### Task 4: Research, strategies/learning, and diagnostics surfaces

**Files:**
- Create: `frontend/src/components/views/ResearchView.tsx`
- Create: `frontend/src/components/views/LearningView.tsx`
- Create: `frontend/src/components/views/DiagnosticsView.tsx`
- Modify: `frontend/src/components/research/ResearchLab.tsx`
- Modify: `frontend/src/components/providers/RouteMatrix.tsx`
- Modify: `frontend/src/components/strategy/StrategyStudio.tsx`
- Test: `frontend/src/tests/components/ResearchView.test.tsx`
- Test: `frontend/src/tests/components/LearningView.test.tsx`
- Test: `frontend/src/tests/components/DiagnosticsView.test.tsx`

**Interfaces:**
- Research displays source/event/published/retrieved/freshness/reliability/relevance/agreement/conflicts and AI summary.
- Learning displays genome parent tree, stages, evaluations, Paper/Live evidence, qualification failures, promotion/canary/rollback/quarantine, and lessons.
- Diagnostics displays explicit liveness/readiness/blockers for Binance, streams, database, OpenCodex route/auth, Hermes, Telegram, reconciliation, backups, and last cycle.

- [ ] **Step 1: Write failing degraded/learning tests**

```tsx
it('renders unavailable quota as unavailable rather than zero', async () => {
  render(<ResearchView />);
  expect(await screen.findByText('Research quota unavailable')).toBeInTheDocument();
  expect(screen.queryByText('0/8')).not.toBeInTheDocument();
});

it('shows why a candidate is not live eligible', async () => {
  render(<LearningView />);
  expect(await screen.findByText('MIN_200_PAPER_TRADES')).toBeInTheDocument();
});
```

- [ ] **Step 2: Verify tests fail**

```powershell
npm --prefix frontend test -- ResearchView.test.tsx LearningView.test.tsx DiagnosticsView.test.tsx
```

- [ ] **Step 3: Implement explicit data states and linked evidence**

```tsx
type Availability = 'available' | 'degraded' | 'unavailable';

function AvailabilityPanel<T>({ section, render }: Props<T>) {
  if (section.availability === 'unavailable' || section.data === null) {
    return <Unavailable detail={section.detail} observedAt={section.observed_at} />;
  }
  return render(section.data, section.availability);
}
```

RouteMatrix discovers models live from OpenCodex, tests connection before save, and never shows/accepts provider keys in GoldGuard.

- [ ] **Step 4: Run all frontend tests/type/build**

```powershell
npm --prefix frontend test
npm --prefix frontend run typecheck
npm --prefix frontend run build
```

- [ ] **Step 5: Commit**

```powershell
git add frontend/src/components/views/ResearchView.tsx frontend/src/components/views/LearningView.tsx frontend/src/components/views/DiagnosticsView.tsx frontend/src/components/research/ResearchLab.tsx frontend/src/components/providers/RouteMatrix.tsx frontend/src/components/strategy/StrategyStudio.tsx frontend/src/tests/components
git commit -m "feat: explain research learning and diagnostics"
```

### Task 5: Telegram delivery, preferences, critical alerts, and daily report

**Files:**
- Create: `backend/goldguard/notifications/__init__.py`
- Create: `backend/goldguard/notifications/models.py`
- Create: `backend/goldguard/notifications/telegram.py`
- Create: `backend/goldguard/services/notification_service.py`
- Create: `backend/goldguard/storage/migrations/008_notifications.sql`
- Create: `backend/goldguard/web/routes/notifications.py`
- Modify: `backend/goldguard/config.py`
- Test: `backend/tests/notifications/test_telegram.py`
- Test: `backend/tests/services/test_notification_service.py`
- Test: `backend/tests/web/test_notifications_api.py`

**Interfaces:**
- `NotificationService.publish(event)`, `send_test(principal)`, `send_daily_report(day)`.
- Category preferences are in the profile; critical categories override mute while Telegram is enabled.
- Routes: `GET /api/notifications/status`, `POST /api/notifications/test`.

- [ ] **Step 1: Write failing critical/redaction/idempotency tests**

```python
async def test_critical_alert_ignores_user_mute(service, telegram) -> None:
    await service.publish(event("PROTECTION_FAILED", category="critical"))
    assert telegram.sent_count == 1


async def test_notification_never_contains_secret(service, telegram) -> None:
    await service.publish(event_with_payload({"api_key": "secret", "detail": "failed"}))
    assert "secret" not in telegram.last_text
```

- [ ] **Step 2: Verify tests fail**

```powershell
$testBase = Join-Path $env:TEMP "pytest-goldguard-telegram-red"
uv run pytest backend/tests/notifications backend/tests/services/test_notification_service.py backend/tests/web/test_notifications_api.py -q -p no:cacheprovider --basetemp $testBase
```

- [ ] **Step 3: Implement bounded Telegram HTTP delivery**

```python
class TelegramClient:
    async def send(self, text: str, dedupe_key: str) -> DeliveryResult:
        safe = self._redactor.redact(text)[:4096]
        return await self._outbox.send_once("telegram", dedupe_key, safe)
```

Use server-side bot token/chat ID, timeout/backoff, persisted outbox/delivery state, rate limiting, Markdown-safe escaping, and no retry storm. Daily report derives from read models and labels Paper/Live.

- [ ] **Step 4: Run notification/web/service suites**

```powershell
$testBase = Join-Path $env:TEMP "pytest-goldguard-telegram-green"
uv run pytest backend/tests/notifications backend/tests/services/test_notification_service.py backend/tests/web/test_notifications_api.py backend/tests/storage -q -p no:cacheprovider --basetemp $testBase
uv run ruff check backend/goldguard/notifications backend/goldguard/services/notification_service.py backend/goldguard/web/routes/notifications.py backend/tests/notifications
uv run mypy backend/goldguard/notifications backend/goldguard/services/notification_service.py backend/goldguard/web/routes/notifications.py
```

- [ ] **Step 5: Commit**

```powershell
git add backend/goldguard/notifications backend/goldguard/services/notification_service.py backend/goldguard/storage/migrations/008_notifications.sql backend/goldguard/web/routes/notifications.py backend/goldguard/config.py backend/tests/notifications backend/tests/services/test_notification_service.py backend/tests/web/test_notifications_api.py
git commit -m "feat: send configurable telegram alerts"
```

### Task 6: Responsive layout, all-tab Playwright journeys, and accessibility

**Files:**
- Modify: `frontend/src/App.tsx`
- Modify: `frontend/src/index.css`
- Modify: `frontend/src/components/layout/Sidebar.tsx`
- Modify: `frontend/src/components/layout/TopHeader.tsx`
- Create: `frontend/e2e/autonomous-dashboard.spec.ts`
- Create: `frontend/e2e/settings-live-arming.spec.ts`
- Create: `frontend/e2e/degraded-states.spec.ts`
- Create: `frontend/playwright.config.ts`

**Interfaces:**
- Desktop and mobile navigation exposes Overview, Markets, Orders, Positions/Holdings, History, Research, Learning, Diagnostics, Settings.
- Every interactive control has accessible name, keyboard focus, modal focus containment, confirmation, and visible Paper/Live state.

- [ ] **Step 1: Write failing desktop/mobile journeys**

```ts
test('all tabs render truthful state on mobile', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto('/');
  for (const name of ['Overview','Markets','Orders','Positions','History','Research','Learning','Diagnostics']) {
    await page.getByRole('link', { name }).click();
    await expect(page.getByRole('heading', { name })).toBeVisible();
  }
  await expect(page.locator('[data-mode="paper"]')).toBeVisible();
});
```

- [ ] **Step 2: Run Playwright and capture failures**

```powershell
npm --prefix frontend run e2e -- autonomous-dashboard.spec.ts settings-live-arming.spec.ts degraded-states.spec.ts
```

- [ ] **Step 3: Implement responsive navigation and state treatments**

Use CSS grid/flex breakpoints, scroll-safe tables/cards, focus trapping/restoration, reduced-motion support, and no horizontal page overflow at 390px. Do not duplicate backend business calculations in React.

- [ ] **Step 4: Run Gate 6 verification**

```powershell
npm --prefix frontend test
npm --prefix frontend run typecheck
npm --prefix frontend run build
npm --prefix frontend run e2e
$testBase = Join-Path $env:TEMP "pytest-goldguard-gate6"
uv run pytest backend/tests/readmodels backend/tests/notifications backend/tests/web -q -p no:cacheprovider --basetemp $testBase
git diff --check
```

- [ ] **Step 5: Commit**

```powershell
git add frontend/src/App.tsx frontend/src/index.css frontend/src/components/layout frontend/e2e frontend/playwright.config.ts
git commit -m "test: prove autonomous dashboard on desktop and mobile"
```
