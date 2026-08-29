"""FastAPI application entry point for GoldGuard.

Truthfulness contract: every data endpoint answers with
``{availability, source, observed_at, stale, detail, data}``. When a value cannot be
measured the endpoint reports ``unavailable`` with empty data instead of substituting a
plausible number — see backend/tests/web/test_api_truthfulness.py.

Surface:
- Market candles and quotes fed by live ingestion, never generated.
- Strategy Studio backtests that refuse to run without a verified candle series.
- Hermes research quotas, memory reflections, provider routing, decision audit ledger.
- Paper-only cockpit: preflight gate, start/pause/emergency-stop, and a bounded agent
  event feed served both as a snapshot and over Server-Sent Events.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
from collections.abc import AsyncGenerator, Awaitable, Callable
from contextlib import asynccontextmanager, suppress
from datetime import UTC, datetime, timedelta
from decimal import Decimal, InvalidOperation
from pathlib import Path
from time import perf_counter
from typing import Annotated, Any

import httpx
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, SecretStr, StringConstraints

from goldguard.ai.decision import DecisionVetoEngine
from goldguard.backtest.engine import BacktestEngine, FrictionConfig
from goldguard.backtest.walk_forward import WalkForwardHarness
from goldguard.broker.paper import PaperBroker
from goldguard.config import Settings
from goldguard.context.calendar import EconomicCalendar
from goldguard.context.engine import ContextEngine
from goldguard.context.playbook import ProfessionalChecklist
from goldguard.context.sources import OpenCodexSearchProvider
from goldguard.domain.defaults import SAFE_DEFAULT_V1, strategy_settings_from_app
from goldguard.hermes.generator import StrategyProposalGenerator
from goldguard.hermes.loop import HermesLoopConfig, HermesResearchLoop
from goldguard.live.arming import ArmingService, configure_arming_service
from goldguard.market.binance import BinancePublicClient
from goldguard.market.dataset_service import DatasetService
from goldguard.market.live_stream import CHART_INTERVALS, candle_payload
from goldguard.memory.engine import MemoryBank
from goldguard.observability.events import AgentEvent
from goldguard.providers.client import AuthenticationError, GatewayClient, GatewayUnavailableError
from goldguard.providers.service import RouteService
from goldguard.risk.engine import RiskEngine
from goldguard.risk.state_machine import StateMachine
from goldguard.security.service import AuthService
from goldguard.services.ingestion import MarketIngestionService, MarketSnapshot
from goldguard.services.promotion_controller import (
    CanaryEvent,
    EvidenceDataset,
    PromotionController,
    ShadowEvidence,
)
from goldguard.services.runtime import TradingRuntime
from goldguard.services.settings_service import (
    SettingsService,
    configure_settings_service,
)
from goldguard.storage.database import Database
from goldguard.storage.profile_repository import ProfileRepository
from goldguard.storage.repositories import (
    AutonomyRepository,
    EvaluationRepository,
    GenomeRepository,
    LedgerRepository,
    MarketCandleRepository,
    PromotionRepository,
    ProviderRepository,
    QuotaRepository,
    ReflectionRepository,
)
from goldguard.strategy.genome import (
    StrategyGenome,
    genome_hash,
    trend_pullback_v1,
)
from goldguard.strategy.indicators import (
    atr_wilder,
    ema_series,
    median_volume_ratio,
    rsi_wilder,
)
from goldguard.strategy.promotion import PromotionPipeline
from goldguard.strategy.runtime import GenomeRuntime
from goldguard.web.auth_dependencies import configure_auth_service
from goldguard.web.routes.auth import router as auth_router
from goldguard.web.routes.control import router as control_router
from goldguard.web.routes.execution import router as execution_router
from goldguard.web.routes.qualification import router as qualification_router
from goldguard.web.routes.research import router as research_router
from goldguard.web.routes.settings import router as settings_router

logger = logging.getLogger("goldguard.web")

AGENT_EVENT_DISPLAY_LIMIT = 30
SSE_HEARTBEAT_SECONDS = 15.0
CANDLE_PAGE_LIMIT = 500

# ---------------------------------------------------------------------------
# Application Singletons
# ---------------------------------------------------------------------------
_settings: Settings | None = None
_db: Database | None = None
_genome_repo: GenomeRepository | None = None
_ledger_repo: LedgerRepository | None = None
_quota_repo: QuotaRepository | None = None
_provider_repo: ProviderRepository | None = None
_reflection_repo: ReflectionRepository | None = None
_candle_repo: MarketCandleRepository | None = None
_profile_repo: ProfileRepository | None = None
_settings_service: SettingsService | None = None
_auth_service: AuthService | None = None

_broker: PaperBroker | None = None
_risk_engine: RiskEngine | None = None
_runtime: GenomeRuntime | None = None
_trading_runtime: TradingRuntime | None = None
_backtest_engine: BacktestEngine | None = None
_bot_state_machine: StateMachine | None = None
_ingestion: MarketIngestionService | None = None
_provider_http_client: httpx.AsyncClient | None = None
_autonomy_repo: AutonomyRepository | None = None
_promotion_repo: PromotionRepository | None = None
_promotion_controller: PromotionController | None = None
_hermes_loop: HermesResearchLoop | None = None
_hermes_http_client: httpx.AsyncClient | None = None
_calendar: EconomicCalendar | None = None
_dataset_service: DatasetService | None = None
_background_tasks: list[asyncio.Task[None]] = []

# Probe results live in memory only: the providers table has no latency column, and a
# latency measured in a previous process is not a fact about this one.
_provider_probes: dict[str, dict[str, Any]] = {}


def _require[T](value: T | None, label: str) -> T:
    if value is None:
        raise HTTPException(status_code=503, detail=f"{label} is not initialised")
    return value


def _overlay_app_settings(settings: Settings, ledger: LedgerRepository) -> Settings:
    stored = ledger.load_active_settings()
    if not stored:
        return settings
    update: dict[str, Any] = {}
    if stored.get("paper_starting_balance") is not None:
        update["paper_starting_balance"] = Decimal(str(stored["paper_starting_balance"]))
    if stored.get("paper_risk_per_trade") is not None:
        update["paper_risk_per_trade"] = Decimal(str(stored["paper_risk_per_trade"]))
    return settings.model_copy(update=update) if update else settings


def _settings_payload(settings: Settings) -> dict[str, Any]:
    return {
        "environment": settings.environment,
        "mode": settings.mode,
        "symbol": settings.symbol,
        "entry_timeframe": settings.entry_timeframe,
        "regime_timeframe": settings.regime_timeframe,
        "paper_starting_balance": str(settings.paper_starting_balance),
        "paper_risk_per_trade": str(settings.paper_risk_per_trade),
        "taker_fee_rate": str(settings.taker_fee_rate),
        "slippage_rate": str(settings.slippage_rate),
        "max_spread_rate": str(settings.maximum_spread_rate),
        "daily_loss_halt": str(SAFE_DEFAULT_V1.daily_loss_halt),
        "emergency_drawdown_halt": str(SAFE_DEFAULT_V1.emergency_drawdown_halt),
        "research_backtest_max_per_day": settings.research_backtest_max_per_day,
        "research_web_calls_max_per_day": settings.research_web_calls_max_per_day,
        "market_ingestion_enabled": settings.market_ingestion_enabled,
        "live_capability_enabled": settings.live_capability_enabled,
        "mutable": True,
        "mutable_fields": ["paper_starting_balance", "paper_risk_per_trade"],
    }


def _get_db() -> Database:
    return _require(_db, "database")


def get_trading_runtime() -> TradingRuntime:
    return _require(_trading_runtime, "trading runtime")


def _autonomy_state() -> dict[str, Any]:
    """Durable autonomy state. Fails closed: an uninitialised store reads as revoked."""
    if _autonomy_repo is None:
        return {
            "full_autonomy": False,
            "revoked_reason": "autonomy store is not initialised",
            "updated_at": None,
        }
    return _autonomy_repo.state()


def _is_full_autonomy() -> bool:
    return bool(_autonomy_state()["full_autonomy"])


def _hermes_dataset(market: MarketSnapshot) -> EvidenceDataset:
    """Build Hermes evidence from verified candles and the durable paper ledger."""
    ledger = _require(_ledger_repo, "ledger repository")
    account = _paper_account_id()
    trades = ledger.list_trades(account) if account else []
    closed = [trade for trade in trades if str(trade["status"]) == "CLOSED"]
    net_pnl = sum(
        (Decimal(str(trade["realized_pnl_text"] or "0")) for trade in closed),
        Decimal("0"),
    )
    opened = [
        datetime.fromisoformat(str(trade["opened_at"]))
        for trade in closed
        if trade["opened_at"]
    ]
    shadow_days = 0
    if opened:
        shadow_days = max((datetime.now(UTC) - min(opened)).days, 0)
    candles, dataset_id = _research_candles(market)
    return EvidenceDataset(
        dataset_id=dataset_id,
        verified=True if dataset_id.startswith("history:") else market.verified,
        candles_15m=tuple(candles),
        shadow=ShadowEvidence(
            days=shadow_days,
            net_pnl=net_pnl,
            trades=len(closed),
            slippage_acceptable=bool(closed),
        ),
    )


def _research_candles(market: MarketSnapshot) -> tuple[tuple[Any, ...], str]:
    settings = _settings
    if _dataset_service is not None and settings is not None:
        try:
            history = _dataset_service.load_verified(settings.symbol, "15m")
        except Exception:
            history = ()
        if len(history) >= 100:
            return history, f"history:{settings.symbol}:verified"
    return tuple(market.candles_15m), (
        f"app:{market.source}:{market.observed_at.isoformat()}"
        if market.observed_at
        else f"app:{market.source}:unobserved"
    )


async def _calendar_worker() -> None:
    cycles = 0
    while True:
        if _calendar is not None:
            await _calendar.refresh()
        if cycles % 2 == 0:
            try:
                await _refresh_ai_context()
            except Exception as exc:
                logger.warning("AI context refresh failed: %s", exc)
        cycles += 1
        await asyncio.sleep(15 * 60)


async def _refresh_ai_context() -> None:
    settings = _settings
    if settings is None or not settings.gateway_base_url or _hermes_http_client is None:
        return
    gateway = GatewayClient(
        base_url=settings.gateway_base_url,
        auth_token=(
            settings.gateway_data_token.get_secret_value()
            if settings.gateway_data_token is not None
            else None
        ),
        http_client=_hermes_http_client,
    )
    engine = ContextEngine(
        search_provider=OpenCodexSearchProvider(gateway),
        quota_repo=_quota_repo,
        max_daily_searches=settings.research_web_calls_max_per_day,
    )
    snapshot = await engine.fetch_snapshot(symbol=settings.symbol)
    if _ledger_repo is not None and snapshot.items:
        _ledger_repo.save_context_snapshot(snapshot=snapshot, freshness="live")
    if _trading_runtime is not None:
        _trading_runtime.set_ai_context(snapshot)


async def _dataset_worker() -> None:
    global _dataset_service
    settings = _settings
    if settings is None:
        return
    async with httpx.AsyncClient(timeout=30.0) as client:
        service = DatasetService(
            BinancePublicClient(http_client=client, base_url=settings.market_base_url),
            settings.data_dir,
        )
        _dataset_service = service
        end = datetime.now(UTC)
        start = end - timedelta(days=365 * 3)
        try:
            logger.info("Bootstrapping 3-year %s dataset from %s", settings.symbol, start.date())
            await service.bootstrap(settings.symbol, start, end)
            logger.info("3-year dataset verified for %s", settings.symbol)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.warning("Dataset bootstrap failed: %s", exc)
        while True:
            await asyncio.sleep(24 * 60 * 60)


async def _hermes_worker() -> None:
    await asyncio.sleep(120)
    while True:
        try:
            if _hermes_loop is not None and _is_full_autonomy():
                market = _market()
                candles, _dataset_id = _research_candles(market)
                if len(candles) >= 100:
                    result = await _hermes_loop.step(
                        candles_15m=candles,
                        market_summary=market.detail or "",
                        dataset=_hermes_dataset(market),
                        now=datetime.now(UTC),
                    )
                    logger.info("Hermes background step: %s", result.status)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.warning("Hermes background step failed: %s", exc)
        await asyncio.sleep(3 * 60 * 60)


def _observe_canary() -> dict[str, Any]:
    """Drive rollback from measured, durable paper data and return current state."""
    if _promotion_repo is None:
        return {"status": "none"}
    canary = _promotion_repo.get_open_canary()
    if canary is None:
        canary = _promotion_repo.get_latest_canary()
        if canary is None:
            return {"status": "none"}
        return {
            "status": str(canary["stage"]),
            "genome_id": str(canary["genome_id"]),
            "baseline_genome_id": str(canary["baseline_genome_id"]),
            "baseline_hash": str(canary["baseline_hash"]),
            "rollback_reason": canary["rollback_reason"],
            "circuit_breaker_tripped": bool(canary["circuit_breaker_tripped"]),
        }
    account = _paper_account_id()
    if _ledger_repo is None or account is None:
        return {
            "status": str(canary["stage"]),
            "genome_id": str(canary["genome_id"]),
            "baseline_genome_id": str(canary["baseline_genome_id"]),
            "baseline_hash": str(canary["baseline_hash"]),
            "rollback_reason": canary["rollback_reason"],
            "circuit_breaker_tripped": bool(canary["circuit_breaker_tripped"]),
        }
    quote = _market().latest_quote
    equity = _broker.equity(quote) if _broker is not None and quote is not None else (
        _broker.cash if _broker is not None else Decimal("0")
    )
    measured = _ledger_repo.measure_risk_inputs(account, equity=equity)
    opened_at = datetime.fromisoformat(str(canary["opened_at"]))
    error_count = _ledger_repo.count_runtime_errors_since(opened_at)
    if _promotion_controller is not None:
        _promotion_controller.on_canary_event(
            CanaryEvent(
                genome_id=str(canary["genome_id"]),
                drawdown=measured.peak_drawdown_rate,
                error_count=error_count,
                trades=measured.trade_count,
            )
        )
        canary = _promotion_repo.get_canary(str(canary["genome_id"])) or canary
    return {
        "status": str(canary["stage"]),
        "genome_id": str(canary["genome_id"]),
        "baseline_genome_id": str(canary["baseline_genome_id"]),
        "baseline_hash": str(canary["baseline_hash"]),
        "rollback_reason": canary["rollback_reason"],
        "circuit_breaker_tripped": bool(canary["circuit_breaker_tripped"]),
        "drawdown": str(measured.peak_drawdown_rate),
        "error_count": error_count,
        "trades": measured.trade_count,
    }


# ---------------------------------------------------------------------------
# Envelope helpers
# ---------------------------------------------------------------------------
def _env(
    data: Any,
    *,
    availability: str = "available",
    source: str = "sqlite",
    observed_at: datetime | None = None,
    stale: bool = False,
    detail: str | None = None,
) -> dict[str, Any]:
    """Wrap a payload with its provenance so the UI can never mistake a gap for a value."""
    return {
        "availability": availability,
        "source": source,
        "observed_at": (observed_at or datetime.now(UTC)).isoformat(),
        "stale": stale,
        "detail": detail,
        "data": data,
    }


_UNAVAILABLE_MARKET = MarketSnapshot(
    availability="unavailable",
    source="unconfigured",
    observed_at=None,
    stale=True,
    detail="market ingestion is not initialised",
    verified=False,
    candles_15m=(),
    candles_1h=(),
    latest_quote=None,
    filters=None,
)


def _market() -> MarketSnapshot:
    return _ingestion.snapshot() if _ingestion is not None else _UNAVAILABLE_MARKET


def _jsonable(value: Any) -> Any:
    """Coerce Decimals/datetimes inside free-form event payloads into JSON scalars."""
    return json.loads(json.dumps(value, default=str))


def _event_payload(event: AgentEvent) -> dict[str, Any]:
    return {
        "event_id": event.event_id,
        "action": event.action,
        "reason": event.reason,
        "reason_codes": list(event.reason_codes),
        "payload": _jsonable(dict(event.payload)),
        "occurred_at": event.occurred_at.isoformat(),
        "audit_worthy": event.audit_worthy,
    }


def _fingerprint(secret: SecretStr | None) -> str:
    if secret is None:
        return "not-configured"
    digest = hashlib.sha256(secret.get_secret_value().encode()).hexdigest()
    return f"sha256:{digest[:8]}"


def _gateway_client() -> GatewayClient | None:
    """Build a client only when this process actually has a gateway URL and HTTP pool."""
    if _provider_http_client is None or _settings is None or not _settings.gateway_base_url:
        return None
    token = (
        _settings.gateway_data_token.get_secret_value()
        if _settings.gateway_data_token is not None
        else None
    )
    return GatewayClient(
        base_url=_settings.gateway_base_url,
        auth_token=token,
        http_client=_provider_http_client,
    )


def _paper_account_id() -> str | None:
    if _trading_runtime is not None:
        return _trading_runtime.status().paper_account_id
    return _ledger_repo.current_paper_session_id() if _ledger_repo else None


# ---------------------------------------------------------------------------
# Lifespan Initialization
# ---------------------------------------------------------------------------
@asynccontextmanager
async def lifespan(app: FastAPI):  # type: ignore[no-untyped-def]
    global _settings, _db, _genome_repo, _ledger_repo, _candle_repo
    global _quota_repo, _provider_repo, _reflection_repo, _autonomy_repo, _promotion_repo
    global _broker, _risk_engine, _runtime, _trading_runtime, _backtest_engine, _bot_state_machine
    global _ingestion, _provider_http_client, _hermes_http_client
    global _promotion_controller, _hermes_loop
    global _calendar, _dataset_service, _background_tasks

    _promotion_controller = None
    _hermes_loop = None
    _hermes_http_client = None
    _calendar = EconomicCalendar()
    _dataset_service = None
    _background_tasks = []

    try:
        _settings = Settings()
    except Exception as exc:
        logger.error("Failed to load settings from environment: %s", exc)
        _settings = Settings(environment="development")

    data_dir = _settings.data_dir
    try:
        data_dir.mkdir(parents=True, exist_ok=True)
        test_file = data_dir / ".perm_check"
        test_file.touch()
        test_file.unlink()
    except (OSError, PermissionError):
        logger.warning("Directory %s is not writable, falling back to /app/data", data_dir)
        data_dir = Path("/app/data")
        data_dir.mkdir(parents=True, exist_ok=True)
    db_path = data_dir / "goldguard.db"
    logger.info(
        "Starting GoldGuard — env=%s mode=%s db=%s",
        _settings.environment,
        _settings.mode,
        db_path,
    )

    try:
        _db = Database(db_path)
        _db.migrate()

        _genome_repo = GenomeRepository(_db)
        _ledger_repo = LedgerRepository(_db)
        _settings = _overlay_app_settings(_settings, _ledger_repo)
        _quota_repo = QuotaRepository(_db)
        _provider_repo = ProviderRepository(_db)
        _reflection_repo = ReflectionRepository(_db)
        _candle_repo = MarketCandleRepository(_db)
        _autonomy_repo = AutonomyRepository(_db)
        _promotion_repo = PromotionRepository(_db)
        _profile_repo = ProfileRepository(_db)
        _settings_service = SettingsService(_profile_repo)
        configure_settings_service(_settings_service)
        _auth_service = AuthService(_db, production=_settings.environment == "production")
        configure_auth_service(_auth_service)
        _arming_service = ArmingService(_db, _profile_repo, _auth_service)
        configure_arming_service(_arming_service)
        _arming_service.on_restart()

        if _genome_repo.get_active_genome() is None:
            baseline = trend_pullback_v1()
            _genome_repo.save_genome(baseline, origin="baseline", status="active")
            logger.info("Saved baseline strategy genome: %s", baseline.genome_id)

        # Fingerprints are re-derived every boot so a rotated key never shows a stale digest.
        _provider_repo.upsert_provider(
            name="opencodex",
            kind="proxy",
            base_url=_settings.gateway_base_url or "http://localhost:10100",
            key_fingerprint=_fingerprint(_settings.gateway_data_token),
            status="active" if _settings.gateway_base_url else "unconfigured",
        )

        if not _provider_repo.get_active_routes():
            for role in ("decision", "context", "hermes"):
                _provider_repo.set_route(
                    role, "opencodex", "google-antigravity/gemini-3.7-flash", pinned=True
                )

        current_session = _ledger_repo.current_paper_session_id()
        if current_session is None:
            session_id = _ledger_repo.create_paper_session(_settings.paper_starting_balance)
            logger.info("Created initial paper session: %s", session_id)
        else:
            session = _ledger_repo.get_paper_session(current_session)
            trades = _ledger_repo.list_trades(current_session)
            if (
                session is not None
                and not trades
                and session.initial_balance != _settings.paper_starting_balance
            ):
                session_id = _ledger_repo.create_paper_session(_settings.paper_starting_balance)
                logger.info(
                    "Reset unused paper session from %s to %s: %s",
                    session.initial_balance,
                    _settings.paper_starting_balance,
                    session_id,
                )
    except Exception as exc:
        logger.error("Database migration error (degraded mode): %s", exc, exc_info=True)

    _broker = PaperBroker(
        starting_cash=_settings.paper_starting_balance,
        fee_rate=_settings.taker_fee_rate,
        slippage_rate=_settings.slippage_rate,
    )
    _risk_engine = RiskEngine(strategy_settings_from_app(_settings))
    _runtime = GenomeRuntime()
    _backtest_engine = BacktestEngine(
        FrictionConfig(
            commission_rate=_settings.taker_fee_rate,
            slippage_rate=_settings.slippage_rate,
        )
    )
    _bot_state_machine = StateMachine()

    ai_veto = None
    # Reset per-process caches so a restarted app never reports the previous run's probes
    # or hands out an already-closed HTTP client.
    _provider_http_client = None
    _provider_probes.clear()
    if _provider_repo is not None and _settings.gateway_base_url:
        _provider_http_client = httpx.AsyncClient()
        ai_veto = DecisionVetoEngine(
            route_service=RouteService(_provider_repo),
            gateway_client=GatewayClient(
                base_url=_settings.gateway_base_url,
                auth_token=(
                    _settings.gateway_data_token.get_secret_value()
                    if _settings.gateway_data_token is not None
                    else None
                ),
                http_client=_provider_http_client,
            ),
        )

    if (
        _db is not None
        and _broker is not None
        and _genome_repo is not None
        and _ledger_repo is not None
    ):
        # The runtime starts with no market inputs; ingestion is the only thing that
        # unblocks it, so a boot without market access stays visibly degraded.
        _trading_runtime = TradingRuntime(
            database=_db,
            settings=_settings,
            broker=_broker,
            genome_repo=_genome_repo,
            ledger_repo=_ledger_repo,
            strategy_runtime=_runtime,
            risk_engine=_risk_engine,
            filters=None,
            state_machine=_bot_state_machine,
            candles_15m=[],
            candles_1h=[],
            latest_quote=None,
            checklist=ProfessionalChecklist(),
            ai_veto=ai_veto,
            market_source="startup-degraded",
            market_verified=False,
            calendar=_calendar,
        )

    # Hermes and promotion are built from the same durable repositories as the runtime.
    # The loop receives verified market data at each step; it never manufactures a series.
    if (
        _db is not None
        and _genome_repo is not None
        and _quota_repo is not None
        and _reflection_repo is not None
        and _promotion_repo is not None
        and _autonomy_repo is not None
        and _backtest_engine is not None
    ):
        _hermes_http_client = httpx.AsyncClient()
        hermes_gateway = GatewayClient(
            base_url=_settings.gateway_base_url or "http://127.0.0.1:9",
            auth_token=(
                _settings.gateway_data_token.get_secret_value()
                if _settings.gateway_data_token is not None
                else None
            ),
            http_client=_hermes_http_client,
        )
        pipeline = PromotionPipeline(
            genome_repo=_genome_repo,
            eval_repo=EvaluationRepository(_db),
            promotion_repo=_promotion_repo,
        )
        _promotion_controller = PromotionController(
            pipeline=pipeline,
            genome_repo=_genome_repo,
            promotion_repo=_promotion_repo,
            autonomy_repo=_autonomy_repo,
            engine=_backtest_engine,
            harness=WalkForwardHarness(
                FrictionConfig(
                    commission_rate=_settings.taker_fee_rate,
                    slippage_rate=_settings.slippage_rate,
                )
            ),
        )
        _hermes_loop = HermesResearchLoop(
            proposal_generator=StrategyProposalGenerator(hermes_gateway),
            backtest_engine=_backtest_engine,
            wf_harness=WalkForwardHarness(
                FrictionConfig(
                    commission_rate=_settings.taker_fee_rate,
                    slippage_rate=_settings.slippage_rate,
                )
            ),
            promotion_pipeline=pipeline,
            genome_repo=_genome_repo,
            quota_repo=_quota_repo,
            memory_bank=MemoryBank(_reflection_repo),
            autonomy_repo=_autonomy_repo,
            promotion_controller=_promotion_controller,
            config=HermesLoopConfig(
                max_iterations_per_day=8,
                max_backtest_calls=_settings.research_backtest_max_per_day,
                max_web_calls=_settings.research_web_calls_max_per_day,
            ),
        )

    if _trading_runtime is not None and _candle_repo is not None:
        _ingestion = MarketIngestionService(
            settings=_settings,
            runtime=_trading_runtime,
            candle_repo=_candle_repo,
        )
        await _ingestion.start()

    if _settings is not None and _settings.environment != "test":
        _background_tasks = [
            asyncio.create_task(_calendar_worker(), name="goldguard-calendar"),
            asyncio.create_task(_dataset_worker(), name="goldguard-dataset"),
            asyncio.create_task(_hermes_worker(), name="goldguard-hermes"),
        ]

    yield

    for task in _background_tasks:
        task.cancel()
        with suppress(asyncio.CancelledError, Exception):
            await task
    _background_tasks = []
    if _ingestion is not None:
        await _ingestion.aclose()
    if _trading_runtime is not None:
        _trading_runtime.shutdown()
    if _provider_http_client is not None:
        await _provider_http_client.aclose()
    if _hermes_http_client is not None:
        await _hermes_http_client.aclose()
    logger.info("GoldGuard shutdown complete")


# ---------------------------------------------------------------------------
# FastAPI Application
# ---------------------------------------------------------------------------
app = FastAPI(
    title="GoldGuard",
    description="Autonomous PAXG/USDT Paper Trading Platform & Strategy Studio",
    version="0.1.0",
    lifespan=lifespan,
)

app.include_router(auth_router)
app.include_router(settings_router)
app.include_router(control_router)
app.include_router(research_router)
app.include_router(execution_router)
app.include_router(qualification_router)

app.add_middleware(
    CORSMiddleware,
    allow_origins=list(_settings.cors_origins) if _settings is not None else ["*"],
    allow_credentials=True,
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type", "X-CSRF-Token"],
)


# ---------------------------------------------------------------------------
# 1. Health & Status
# ---------------------------------------------------------------------------
@app.get("/api/health")
async def health() -> dict[str, Any]:
    """Process health probe. Raw (not enveloped) so container health checks stay simple."""
    results: dict[str, Any] = {"status": "ok", "timestamp": datetime.now(UTC).isoformat()}
    if _db is None:
        results["status"] = "starting"
        results["database"] = "uninitialized"
        return results

    try:
        results["database"] = _db.integrity_check()
    except Exception as exc:
        results["database"] = f"FAIL: {exc}"
        results["status"] = "degraded"

    if _quota_repo is not None:
        today = datetime.now(UTC).strftime("%Y-%m-%d")
        backtests, web_calls = _quota_repo.get_usage(today)
        results["quota"] = {"backtests_today": backtests, "web_calls_today": web_calls}

    results["bot_running"] = _trading_runtime.status().running if _trading_runtime else False
    results["market"] = _market().availability
    return results


@app.get("/api/status")
async def app_status() -> dict[str, Any]:
    """Runtime mode, active strategy, and autonomy configuration."""
    settings = _require(_settings, "settings")
    active_genome = _genome_repo.get_active_genome() if _genome_repo else None
    runtime_status = _trading_runtime.status() if _trading_runtime else None
    market = _market()
    return _env(
        {
            "environment": settings.environment,
            "mode": settings.mode,
            "symbol": settings.symbol,
            "bot_running": runtime_status.running if runtime_status else False,
            "bot_state": runtime_status.state.value if runtime_status else None,
            "full_autonomy": _is_full_autonomy(),
            "active_genome_id": active_genome.genome_id if active_genome else None,
            "paper_balance": str(_broker.cash) if _broker else None,
            "live_enabled": settings.live_capability_enabled,
            "market_source": market.source,
            "market_verified": market.verified,
            "canary": _observe_canary(),
            "degraded_reasons": list(runtime_status.degraded_reasons) if runtime_status else [],
        },
        source="runtime",
        availability="available" if runtime_status else "degraded",
        detail=None if runtime_status else "trading runtime failed to initialise",
    )


# ---------------------------------------------------------------------------
# 2. KPI cards
# ---------------------------------------------------------------------------
def _max_drawdown_percent(values: list[float]) -> float | None:
    """Peak-to-trough decline across recorded snapshots. None until there is history."""
    if len(values) < 2:
        return None
    peak = values[0]
    worst = 0.0
    for value in values:
        peak = max(peak, value)
        if peak > 0:
            worst = max(worst, (peak - value) / peak)
    return round(worst * 100, 2)


@app.get("/api/kpi")
async def kpi() -> dict[str, Any]:
    """Overview cards. Any figure that needs data we do not have is reported as null."""
    settings = _require(_settings, "settings")
    broker = _require(_broker, "paper broker")
    market = _market()
    quote = market.latest_quote

    if quote is not None:
        equity: float | None = float(broker.equity(quote))
    elif broker.position is None:
        equity = float(broker.cash)  # flat: equity is exactly cash, no mark-to-market needed
    else:
        equity = None

    account = _paper_account_id()
    snapshots = _ledger_repo.list_equity_snapshots(account) if _ledger_repo and account else []
    values = [float(Decimal(str(row["equity_text"]))) for row in snapshots]
    cutoff = (datetime.now(UTC) - timedelta(hours=24)).isoformat()
    reference = next(
        (
            value
            for row, value in zip(snapshots, values, strict=True)
            if str(row["observed_at"]) >= cutoff
        ),
        None,
    )

    start_balance = float(settings.paper_starting_balance)
    total_pnl = round(equity - start_balance, 2) if equity is not None else None
    total_pnl_percent = (
        round(total_pnl / start_balance * 100, 2)
        if total_pnl is not None and start_balance
        else None
    )
    change_percent = (
        round((equity - reference) / reference * 100, 2)
        if equity is not None and reference
        else None
    )

    return _env(
        {
            "equity": round(equity, 2) if equity is not None else None,
            "equityCurrency": "USDT",
            "equityChangePercent": change_percent,
            "equityChangePeriod": "24H",
            "cash": round(float(broker.cash), 2),
            "cashCurrency": "USDT",
            "cashChangeNote": "Paper Mode" if settings.mode == "paper" else "Live Active",
            "totalPnl": total_pnl,
            "totalPnlCurrency": "USDT",
            "totalPnlChangePercent": total_pnl_percent,
            "totalPnlChangePeriod": "Since start",
            "maxDrawdown": _max_drawdown_percent(values),
            "maxDrawdownPeriod": f"{len(values)} recorded snapshots",
            "liveSpread": round(float(quote.ask - quote.bid), 2) if quote else None,
            "liveSpreadCurrency": "USDT",
        },
        source="paper-ledger",
        availability="available" if quote is not None else "degraded",
        observed_at=quote.observed_at if quote else None,
        stale=market.stale,
        detail=None if quote is not None else "spread and drawdown need live market data",
    )


# ---------------------------------------------------------------------------
# 3. Market candles & quotes
# ---------------------------------------------------------------------------
@app.get("/api/market/candles")
async def market_candles(
    symbol: str = "PAXGUSDT",
    interval: str = "15m",
    limit: int = 50,
) -> dict[str, Any]:
    """Ingested candles with real EMA/RSI/ATR. Empty until a real series exists.

    15m/1h are the strategy series (closed bars). Other intervals are chart-only
    Binance public klines plus the forming bar — they never drive entries.
    """
    if interval not in CHART_INTERVALS:
        raise HTTPException(
            status_code=400, detail="interval must be one of 1m, 5m, 15m, 1h, 4h, 1d"
        )
    limit = max(1, min(limit, CANDLE_PAGE_LIMIT))
    market = _market()
    candles: list[Any]
    source = market.source
    if interval == "15m":
        stored = market.candles_15m
    elif interval == "1h":
        stored = market.candles_1h
    else:
        stored = ()
    if stored:
        candles = list(stored)
        forming = _ingestion.hub.forming.get(interval) if _ingestion is not None else None
        if forming is not None:
            if candles and candles[-1].open_time == forming.open_time:
                candles[-1] = forming
            elif not forming.closed:
                candles.append(forming)
    elif _ingestion is not None and market.availability != "unavailable":
        try:
            candles = await _ingestion.chart_candles(interval, limit)
            source = "binance-chart"
        except Exception as exc:
            return _env(
                [],
                availability="unavailable",
                source=market.source,
                stale=True,
                detail=f"chart klines unavailable: {exc}",
            )
    else:
        candles = []
    if not candles:
        return _env(
            [],
            availability="unavailable",
            source=source,
            stale=True,
            detail=market.detail or f"no verified {interval} candles have been ingested yet",
        )

    closes = [float(candle.close) for candle in candles]
    highs = [float(candle.high) for candle in candles]
    lows = [float(candle.low) for candle in candles]
    volumes = [float(candle.volume) for candle in candles]
    ema20 = ema_series(closes, 20)
    ema50 = ema_series(closes, 50)
    rsi14 = rsi_wilder(closes, 14)
    atr14 = atr_wilder(highs, lows, closes, 14)

    rows: list[dict[str, Any]] = []
    for index in range(max(len(candles) - limit, 0), len(candles)):
        candle = candles[index]
        row = candle_payload(candle)
        row.update(
            {
                "ema20": round(ema20[index], 2),
                "ema50": round(ema50[index], 2),
                "rsi14": None if rsi14[index] is None else round(float(rsi14[index] or 0.0), 2),
                "atr14": None if atr14[index] is None else round(float(atr14[index] or 0.0), 4),
                "volumeRatio": (
                    round(median_volume_ratio(volumes[: index + 1]), 3) if index >= 19 else None
                ),
            }
        )
        rows.append(row)

    return _env(
        rows,
        availability=market.availability if interval in ("15m", "1h") else "available",
        source=source,
        observed_at=candles[-1].close_time,
        stale=market.stale,
        detail=market.detail,
    )


@app.get("/api/market/quote")
async def market_quote(symbol: str = "PAXGUSDT") -> dict[str, Any]:
    """Latest ingested bid/ask. Null until a quote has actually been observed."""
    market = _market()
    quote = market.latest_quote
    if quote is None:
        return _env(
            None,
            availability="unavailable",
            source=market.source,
            stale=True,
            detail=market.detail or "no live quote has been observed yet",
        )
    spread = quote.ask - quote.bid
    mid = (quote.ask + quote.bid) / Decimal("2")
    return _env(
        {
            "symbol": symbol,
            "bid": float(quote.bid),
            "ask": float(quote.ask),
            "spread": float(spread),
            "spread_rate": float(spread / mid) if mid > 0 else None,
            "observed_at": quote.observed_at.isoformat(),
        },
        availability=market.availability,
        source=market.source,
        observed_at=quote.observed_at,
        stale=market.stale,
        detail=market.detail,
    )


@app.get("/api/market/stream")
async def market_stream() -> StreamingResponse:
    """SSE: live bid/ask and forming klines from Binance public WebSocket. No API key."""

    async def frames() -> AsyncGenerator[str, None]:
        if _ingestion is None:
            yield _sse("snapshot", {"quote": None, "forming": {}, "source": "unconfigured"})
            return
        hub = _ingestion.hub
        queue = hub.subscribe()
        try:
            yield _sse("snapshot", hub.snapshot())
            while True:
                try:
                    event = await asyncio.wait_for(queue.get(), timeout=SSE_HEARTBEAT_SECONDS)
                except TimeoutError:
                    yield ": heartbeat\n\n"
                    continue
                name = str(event.get("type") or "tick")
                yield _sse(name, event)
        finally:
            hub.unsubscribe(queue)

    return StreamingResponse(
        frames(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-store", "X-Accel-Buffering": "no"},
    )


# ---------------------------------------------------------------------------
# 4. Open position & decision pipeline
# ---------------------------------------------------------------------------
_PIPELINE_STEPS: tuple[tuple[str, str], ...] = (
    ("strategy", "Strategy signal"),
    ("context", "Context checklist"),
    ("ai", "AI veto"),
    ("risk", "Risk sizing"),
    ("execution", "Paper fill"),
)

# Stage (1-indexed) each outcome reached, and whether that stage let the trade through.
_PIPELINE_OUTCOMES: dict[str, tuple[int, bool]] = {
    "NO_ACTION": (1, False),
    "CHECKLIST_HELD": (2, False),
    "AI_VETO_REJECTED": (3, False),
    "MARKET_FILTERS_UNAVAILABLE": (4, False),
    "RISK_REJECTED": (4, False),
    "ENTRY_FILLED": (5, True),
    "EXIT_TRIGGERED": (5, True),
}


def _latest_decision_event() -> AgentEvent | None:
    if _trading_runtime is None:
        return None
    for event in reversed(_trading_runtime.recent_events(AGENT_EVENT_DISPLAY_LIMIT)):
        if "outcome_action" in event.payload:
            return event
    return None


def _pipeline_steps() -> list[dict[str, Any]]:
    """Rebuild the 5-gate card from the last real decision instead of guessing."""
    event = _latest_decision_event()
    if event is None:
        return [
            {
                "stepNumber": number,
                "id": identifier,
                "label": label,
                "status": "pending",
                "detail": "No closed candle has been evaluated yet.",
            }
            for number, (identifier, label) in enumerate(_PIPELINE_STEPS, start=1)
        ]

    action = str(event.payload.get("outcome_action", ""))
    reached, passed = _PIPELINE_OUTCOMES.get(action, (0, False))
    codes = ", ".join(event.reason_codes) or action or "no reason recorded"
    steps: list[dict[str, Any]] = []
    for number, (identifier, label) in enumerate(_PIPELINE_STEPS, start=1):
        if reached == 0:
            status, detail = "pending", f"{event.reason}: {codes}"
        elif number < reached:
            status, detail = "completed", "Passed on the last evaluated candle."
        elif number == reached:
            status = "completed" if passed else "blocked"
            detail = codes
        else:
            status, detail = "pending", "Not reached on the last evaluated candle."
        steps.append(
            {
                "stepNumber": number,
                "id": identifier,
                "label": label,
                "status": status,
                "detail": detail,
            }
        )
    return steps


@app.get("/api/position")
async def position() -> dict[str, Any]:
    """Open paper position, if any. A flat account returns ``position: null``."""
    settings = _require(_settings, "settings")
    broker = _require(_broker, "paper broker")
    market = _market()
    quote = market.latest_quote
    open_position = broker.position
    steps = _pipeline_steps()

    if open_position is None:
        return _env(
            {"hasPosition": False, "position": None, "pipelineSteps": steps},
            source="paper-broker",
            observed_at=quote.observed_at if quote else None,
            stale=market.stale,
        )

    plan = open_position.plan
    entry_price = open_position.entry_fill.price
    unrealized = (
        round(float((quote.bid - entry_price) * open_position.quantity), 2) if quote else None
    )
    equity = broker.equity(quote) if quote else None
    return _env(
        {
            "hasPosition": True,
            "position": {
                "direction": "LONG",
                "isLive": settings.mode == "live",
                "entry": float(entry_price),
                "stop": float(plan.stop),
                "target": float(plan.target),
                "quantity": f"{open_position.quantity} PAXG",
                "riskAmount": float(plan.risk_amount),
                "riskPercent": (
                    round(float(plan.risk_amount / equity * 100), 2)
                    if equity and equity > 0
                    else None
                ),
                "unrealizedPnl": unrealized,
            },
            "pipelineSteps": steps,
        },
        source="paper-broker",
        availability="available" if quote is not None else "degraded",
        observed_at=quote.observed_at if quote else None,
        stale=market.stale,
        detail=None if quote is not None else "unrealised PnL needs a live quote",
    )


# ---------------------------------------------------------------------------
# 5. Equity curve
# ---------------------------------------------------------------------------
@app.get("/api/equity")
async def equity_curve() -> dict[str, Any]:
    """Recorded equity snapshots. Empty until the runtime books its first paper trade."""
    settings = _require(_settings, "settings")
    ledger = _require(_ledger_repo, "ledger repository")
    account = _paper_account_id()
    snapshots = ledger.list_equity_snapshots(account) if account else []
    if not snapshots:
        return _env(
            [],
            availability="unavailable",
            source="paper-ledger",
            stale=True,
            detail="no equity snapshot has been recorded yet",
        )

    baseline = float(settings.paper_starting_balance)
    points = [
        {
            "date": str(row["observed_at"]),
            "label": str(row["observed_at"])[5:16].replace("T", " "),
            "value": round(float(Decimal(str(row["equity_text"]))), 2),
            "cash": round(float(Decimal(str(row["cash_text"]))), 2),
            "baseline": baseline,
        }
        for row in snapshots
    ]
    return _env(points, source="paper-ledger", observed_at=datetime.now(UTC))


# ---------------------------------------------------------------------------
# 6. Context feed
# ---------------------------------------------------------------------------
@app.get("/api/context")
async def live_context() -> dict[str, Any]:
    """Items from the newest persisted context snapshot. Empty until one is captured."""
    ledger = _require(_ledger_repo, "ledger repository")
    snapshot = ledger.latest_context_snapshot()
    items = snapshot["summary"].get("items", []) if snapshot else []
    if not snapshot or not items:
        if _calendar is not None:
            calendar_rows = _calendar.as_context_rows()
            if calendar_rows:
                return _env(
                    calendar_rows,
                    availability="available" if _calendar.detail is None else "degraded",
                    source=_calendar.source,
                    observed_at=_calendar.updated_at,
                    stale=_calendar.updated_at is None,
                    detail=_calendar.detail or "economic calendar",
                )
        return _env(
            [],
            availability="unavailable",
            source="context-ledger",
            stale=True,
            detail="no context snapshot with items has been captured yet",
        )

    sources = snapshot["sources"]
    fetched_at = datetime.fromisoformat(str(snapshot["fetched_at"]))
    rows: list[dict[str, Any]] = []
    for index, item in enumerate(items):
        source_indexes = item.get("source_indexes") or []
        source_name = "unattributed"
        if source_indexes and source_indexes[0] < len(sources):
            source_name = str(sources[source_indexes[0]]["url"])
        published = item.get("published_at") or snapshot["fetched_at"]
        rows.append(
            {
                "id": f"{snapshot['id']}-{index}",
                "category": str(item.get("driver", "unknown")),
                "title": str(item.get("summary", "")),
                "direction": str(item.get("direction", "neutral")),
                "severity": str(item.get("severity", "low")),
                "contradictory": bool(item.get("contradictory", False)),
                "source": source_name,
                "time": str(published)[11:16],
            }
        )
    return _env(
        rows,
        source="context-ledger",
        observed_at=fetched_at,
        stale=(datetime.now(UTC) - fetched_at) > timedelta(hours=6),
        detail=f"conflict level {snapshot['conflict_level']}",
    )


# ---------------------------------------------------------------------------
# 7. Strategy Studio & deterministic backtesting
# ---------------------------------------------------------------------------
class BacktestRequest(BaseModel):
    genome: dict[str, Any]


_GENOME_INDEX_FIELDS = ("status", "genome_hash", "created_at", "origin", "parent_id")


@app.get("/api/genomes")
async def list_genomes(status_filter: str | None = None) -> dict[str, Any]:
    """Genome registry rows merged with their stored specification."""
    repo = _require(_genome_repo, "genome repository")
    genomes = repo.list_genomes(status=status_filter)
    if not genomes and status_filter is None:
        repo.save_genome(trend_pullback_v1(), origin="baseline", status="active")
        genomes = repo.list_genomes()
    return _env(genomes, source="genome-registry")


@app.get("/api/genomes/{genome_id}")
async def get_genome(genome_id: str) -> dict[str, Any]:
    """Full genome specification plus its registry status."""
    repo = _require(_genome_repo, "genome repository")
    genome = repo.get_genome(genome_id)
    if genome is None:
        raise HTTPException(status_code=404, detail=f"Genome {genome_id} not found")
    row = repo.get_genome_row(genome_id)
    payload = genome.model_dump(mode="json")
    payload["status"] = row["status"] if row else "candidate"
    payload["genome_hash"] = genome_hash(genome)
    return _env(payload, source="genome-registry")


@app.post("/api/genomes/save")
async def save_genome(payload: dict[str, Any]) -> dict[str, Any]:
    """Save a candidate genome. Active and archived specifications are immutable."""
    repo = _require(_genome_repo, "genome repository")
    spec = {key: value for key, value in payload.items() if key not in _GENOME_INDEX_FIELDS}
    try:
        genome = StrategyGenome.model_validate(spec)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Invalid genome specification: {exc}") from exc

    existing_status = repo.get_genome_status(genome.genome_id)
    if existing_status is not None and existing_status != "candidate":
        raise HTTPException(
            status_code=409,
            detail=(
                f"genome {genome.genome_id} is {existing_status} and cannot be edited; "
                "save it under a new genome_id instead"
            ),
        )

    repo.save_genome(genome, origin="user", status="candidate")
    return {
        "status": "saved",
        "genome_id": genome.genome_id,
        "genome_hash": genome_hash(genome),
        "registry_status": "candidate",
    }


@app.post("/api/genomes/promote")
async def promote_genome(payload: dict[str, str]) -> dict[str, Any]:
    """Legacy route intentionally disabled; only PromotionController may activate."""
    raise HTTPException(
        status_code=409,
        detail="direct genome promotion is disabled; PromotionController must run all four gates",
    )


def _decimal_or_none(value: Decimal | None, digits: str = "0.01") -> str | None:
    return None if value is None else str(value.quantize(Decimal(digits)))


@app.post("/api/backtest/run")
async def run_backtest(req: BacktestRequest) -> dict[str, Any]:
    """Deterministic backtest over the ingested series. Refuses to run without one."""
    engine = _require(_backtest_engine, "backtest engine")
    spec = {key: value for key, value in req.genome.items() if key not in _GENOME_INDEX_FIELDS}
    try:
        genome = StrategyGenome.model_validate(spec)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Invalid genome format: {exc}") from exc

    market = _market()
    candles, _ = _research_candles(market)
    if len(candles) < 100 and (not market.verified or len(market.candles_15m) < 100):
        raise HTTPException(
            status_code=409,
            detail=(
                "no verified candle series is loaded — "
                f"have {len(market.candles_15m)} 15m and {len(market.candles_1h)} 1h "
                f"verified={market.verified} from {market.source}. "
                "Bootstrap the dataset before backtesting."
            ),
        )
    settings = _require(_settings, "settings")
    try:
        result = engine.run(
            genome=genome,
            candles_15m=list(candles),
            candles_1h=list(market.candles_1h),
            initial_equity=settings.paper_starting_balance,
        )
    except Exception as exc:
        logger.error("Backtest execution failed: %s", exc, exc_info=True)
        raise HTTPException(status_code=500, detail=f"backtest failed: {exc}") from exc

    report = result.report
    return {
        "net_pnl": f"{report.net_pnl:+0.2f}",
        "gross_pnl": f"{report.gross_pnl:+0.2f}",
        "fee_drag": f"{report.fee_drag:0.2f}",
        "net_return": f"{report.net_return * 100:+0.2f}%",
        "annualized_return": (
            None if report.annualized_return is None else f"{report.annualized_return * 100:+0.2f}%"
        ),
        "buy_and_hold_return": f"{report.buy_and_hold_return * 100:+0.2f}%",
        "trade_count": report.trade_count,
        "win_rate": f"{report.win_rate * 100:0.1f}%",
        "profit_factor": _decimal_or_none(report.profit_factor),
        "expectancy": f"{report.expectancy:+0.2f}",
        "maximum_drawdown": f"{report.maximum_drawdown * 100:0.1f}%",
        "exposure_rate": f"{report.exposure_rate * 100:0.1f}%",
        "sharpe_ratio": _decimal_or_none(report.sharpe_ratio),
        "sortino_ratio": _decimal_or_none(report.sortino_ratio),
        "calmar_ratio": _decimal_or_none(report.calmar_ratio),
        "sample_sufficient": report.sample_sufficient,
        "run_hash": result.run_hash,
        "candles_used": len(market.candles_15m),
        "trades": [
            {
                "side": trade.entry_fill.side.value,
                "entry_price": float(trade.entry_fill.price),
                "exit_price": float(trade.exit_fill.price),
                "pnl": float(trade.realized_pnl),
                "reason": trade.exit_reason.value,
            }
            for trade in result.trades
        ],
    }


# ---------------------------------------------------------------------------
# 8. Hermes research lab
# ---------------------------------------------------------------------------
@app.get("/api/quota")
async def get_quota() -> dict[str, Any]:
    """Today's research quota usage."""
    repo = _require(_quota_repo, "quota repository")
    settings = _require(_settings, "settings")
    today = datetime.now(UTC).strftime("%Y-%m-%d")
    backtests, web_calls = repo.get_usage(today)
    return _env(
        {
            "date": today,
            "backtests_used": backtests,
            "backtests_limit": settings.research_backtest_max_per_day,
            "web_calls_used": web_calls,
            "web_calls_limit": settings.research_web_calls_max_per_day,
        },
        source="quota-ledger",
    )


@app.post("/api/hermes/step")
async def hermes_step() -> dict[str, Any]:
    """Run one autonomous Hermes iteration against verified market evidence."""
    loop = _require(_hermes_loop, "Hermes research loop")
    _require(_settings, "settings")
    if not _is_full_autonomy():
        raise HTTPException(
            status_code=409,
            detail="autonomy is revoked; re-enable autonomy before running research steps",
        )
    market = _market()
    candles, _ = _research_candles(market)
    if len(candles) < 100 and not market.verified:
        raise HTTPException(
            status_code=409,
            detail="Hermes requires verified market candles; ingestion has not supplied them",
        )
    dataset = _hermes_dataset(market)
    result = await loop.step(
        candles_15m=candles,
        market_summary=market.detail or "",
        dataset=dataset,
        now=datetime.now(UTC),
    )
    return {
        "status": result.status,
        "iteration_id": result.iteration_id,
        "candidate_genome_id": result.candidate_genome_id,
        "gate_results": _jsonable(result.gate_results),
        "quota_used": list(result.quota_used),
        "circuit_breaker_tripped": result.circuit_breaker_tripped,
    }


@app.get("/api/reflections")
async def list_reflections(namespace: str | None = None, limit: int = 100) -> dict[str, Any]:
    """Post-mortem lessons written by the runtime. Nothing is seeded at boot."""
    repo = _require(_reflection_repo, "reflection repository")
    rows = repo.list_reflections(namespace=namespace, limit=max(1, min(limit, 200)))
    return _env(
        rows,
        source="memory-bank",
        availability="available" if rows else "unavailable",
        detail=None if rows else "no trade has produced a reflection yet",
    )


@app.get("/api/promotion/canary")
async def promotion_canary() -> dict[str, Any]:
    """Current durable canary state, with rollback driven from measured ledger data."""
    state = _observe_canary()
    return _env(
        state,
        source="promotion-ledger",
        availability="available" if state["status"] != "none" else "unavailable",
        detail=None if state["status"] != "none" else "no promoted canary is recorded",
    )


# ---------------------------------------------------------------------------
# 9. Providers & routing
# ---------------------------------------------------------------------------
def _provider_view() -> list[dict[str, Any]]:
    repo = _require(_provider_repo, "provider repository")
    rows: list[dict[str, Any]] = []
    for provider in repo.list_providers():
        probe = _provider_probes.get(provider.name, {})
        rows.append(
            {
                "name": provider.name,
                "kind": provider.kind,
                "base_url": provider.base_url,
                "key_fingerprint": provider.key_fingerprint,
                "status": provider.status,
                "latency_ms": probe.get("latency_ms"),
                "probe_status": probe.get("probe_status", "unprobed"),
                "probe_detail": probe.get("probe_detail"),
                "last_probe_at": probe.get("probed_at") or provider.last_probe_at,
            }
        )
    return rows


@app.get("/api/providers")
async def list_providers() -> dict[str, Any]:
    """Registered providers. Latency is null until this process has probed them."""
    rows = _provider_view()
    unprobed = sum(1 for row in rows if row["probe_status"] == "unprobed")
    return _env(
        rows,
        source="provider-registry",
        availability="available" if rows else "unavailable",
        detail=(
            f"{unprobed} of {len(rows)} providers have not been probed in this process"
            if unprobed
            else None
        ),
    )


@app.get("/api/routes")
async def list_routes() -> dict[str, Any]:
    """Active model routes for the decision, context, and hermes roles."""
    repo = _require(_provider_repo, "provider repository")
    routes = repo.get_active_routes()
    rows = [
        {
            "id": f"r-{route.role}",
            "role": route.role,
            "provider": route.provider,
            "model": route.model,
            "pinned": route.pinned,
            "version": route.version,
            "status": "active",
        }
        for route in routes.values()
    ]
    return _env(
        rows,
        source="provider-registry",
        availability="available" if rows else "unavailable",
        detail=None if rows else "no route has been configured",
    )


@app.get("/api/providers/catalog")
async def provider_catalog() -> dict[str, Any]:
    """Live model list from OpenCodex. Empty until the gateway answers /v1/models."""
    client = _gateway_client()
    if client is None:
        return _env(
            [],
            availability="unavailable",
            source="opencodex",
            stale=True,
            detail=(
                "OpenCodex is not configured. "
                "Add the second Railway service, then pick models here."
            ),
        )
    try:
        models = await client.list_models()
    except AuthenticationError:
        return _env(
            [],
            availability="unavailable",
            source="opencodex",
            stale=True,
            detail="OpenCodex rejected the shared token. Tokens on both services must match.",
        )
    except GatewayUnavailableError as exc:
        return _env(
            [],
            availability="unavailable",
            source="opencodex",
            stale=True,
            detail=str(exc),
        )
    rows = [
        {
            "id": model.model_id,
            "name": model.display_name or model.model_id,
            "web_search": model.web_search,
            "context_window": model.context_window,
        }
        for model in models
    ]
    return _env(
        rows,
        source="opencodex",
        availability="available" if rows else "unavailable",
        detail=(
            None if rows else (
            "OpenCodex is up but has no models yet. Add a provider in its dashboard."
        )
        ),
    )


class RouteUpdatePayload(BaseModel):
    provider: str
    model: str = "google-antigravity/gemini-3.7-flash"
    pinned: bool = True


@app.post("/api/routes/{role}")
async def set_route(role: str, payload: RouteUpdatePayload) -> dict[str, Any]:
    """Repoint one AI role at a provider/model pair."""
    repo = _require(_provider_repo, "provider repository")
    if role not in ("decision", "context", "hermes"):
        raise HTTPException(status_code=400, detail="role must be decision, context, or hermes")
    version = repo.set_route(role, payload.provider, payload.model, payload.pinned)
    return {
        "role": role,
        "provider": payload.provider,
        "model": payload.model,
        "version": version,
    }


@app.post("/api/providers/probe")
async def probe_providers() -> dict[str, Any]:
    """Measure real round-trip latency. Reports ``unconfigured`` when no gateway exists."""
    repo = _require(_provider_repo, "provider repository")
    providers = repo.list_providers()
    if _provider_http_client is None:
        for provider in providers:
            _provider_probes[provider.name] = {
                "latency_ms": None,
                "probe_status": "unconfigured",
                "probe_detail": "no provider gateway is configured for this process",
                "probed_at": None,
            }
        return _env(
            _provider_view(),
            availability="unavailable",
            source="provider-probe",
            stale=True,
            detail="set GOLDGUARD_GATEWAY_BASE_URL to enable live provider probes",
        )

    now = datetime.now(UTC)
    for provider in providers:
        started = perf_counter()
        try:
            response = await _provider_http_client.get(provider.base_url, timeout=5.0)
            _provider_probes[provider.name] = {
                "latency_ms": int((perf_counter() - started) * 1000),
                "probe_status": "ok" if response.status_code < 500 else "error",
                "probe_detail": f"HTTP {response.status_code}",
                "probed_at": now.isoformat(),
            }
        except Exception as exc:
            _provider_probes[provider.name] = {
                "latency_ms": None,
                "probe_status": "error",
                "probe_detail": str(exc)[:200],
                "probed_at": now.isoformat(),
            }
        repo.record_probe(provider.name, probed_at=now.isoformat())

    rows = _provider_view()
    failed = [row["name"] for row in rows if row["probe_status"] != "ok"]
    return _env(
        rows,
        availability="degraded" if failed else "available",
        source="provider-probe",
        observed_at=now,
        detail=f"unreachable: {', '.join(failed)}" if failed else None,
    )


# ---------------------------------------------------------------------------
# 10. Preflight gate
# ---------------------------------------------------------------------------
def _check(identifier: str, label: str, outcome: str, detail: str) -> dict[str, Any]:
    return {"id": identifier, "label": label, "status": outcome, "detail": detail}


async def _preflight_checks() -> list[dict[str, Any]]:
    """Every gate a beginner must clear before Start does anything, with plain reasons."""
    checks: list[dict[str, Any]] = []

    if _db is None:
        checks.append(_check("database", "Storage", "fail", "The database did not initialise."))
    else:
        try:
            integrity = _db.integrity_check()
        except Exception as exc:
            integrity = f"FAIL: {exc}"
        ok = integrity == "ok"
        checks.append(
            _check(
                "database",
                "Storage",
                "pass" if ok else "fail",
                "Trade ledger is readable and consistent."
                if ok
                else f"Database integrity check returned {integrity}.",
            )
        )

    market = _market()
    runtime_status = _trading_runtime.status() if _trading_runtime else None
    reasons = ", ".join(runtime_status.degraded_reasons) if runtime_status else "runtime missing"
    market_ok = market.availability == "available" and runtime_status is not None and not reasons
    checks.append(
        _check(
            "market_data",
            "Market data",
            "pass" if market_ok else "fail",
            f"Verified {len(market.candles_15m)} 15m and {len(market.candles_1h)} 1h candles "
            f"from {market.source}."
            if market_ok
            else "Waiting for verified PAXGUSDT candles and a live quote "
            f"(source {market.source}; {market.detail or reasons}).",
        )
    )

    active_genome = _genome_repo.get_active_genome() if _genome_repo else None
    checks.append(
        _check(
            "strategy",
            "Active strategy",
            "pass" if active_genome else "fail",
            f"Active genome {active_genome.genome_id}."
            if active_genome
            else "No genome is marked active, so there is no rule set to trade.",
        )
    )

    account = _paper_account_id()
    checks.append(
        _check(
            "paper_account",
            "Paper account",
            "pass" if account else "fail",
            f"Paper session {account} is open."
            if account
            else "No paper session exists to book fills against.",
        )
    )

    if runtime_status is None:
        checks.append(
            _check("runtime", "Runtime", "fail", "The trading runtime failed to initialise.")
        )
    elif runtime_status.rehydration_error is not None:
        checks.append(
            _check(
                "runtime",
                "Runtime",
                "fail",
                f"Stored paper state cannot be rebuilt: {runtime_status.rehydration_error}.",
            )
        )
    elif runtime_status.halted:
        checks.append(
            _check(
                "runtime",
                "Runtime",
                "fail",
                "Emergency stop is engaged. Reset it deliberately; Start will not clear it.",
            )
        )
    else:
        checks.append(_check("runtime", "Runtime", "pass", f"State {runtime_status.state.value}."))

    settings = _settings
    require_gateway = settings is not None and settings.environment != "test"
    client = _gateway_client()
    if client is None:
        checks.append(
            _check(
                "ai_veto",
                "AI brain (OpenCodex)",
                "fail" if require_gateway else "warn",
                "OpenCodex is not configured. Paper trading waits until the second Railway "
                "service is up and OPENCODEX_BASE_URL points at it."
                if require_gateway
                else "No AI gateway in this test process. Deterministic strategy still applies.",
            )
        )
    else:
        try:
            await client.healthz()
            checks.append(
                _check(
                    "ai_veto",
                    "AI brain (OpenCodex)",
                    "pass",
                    "OpenCodex answered /healthz. Pick models on the Providers tab.",
                )
            )
        except AuthenticationError:
            checks.append(
                _check(
                    "ai_veto",
                    "AI brain (OpenCodex)",
                    "fail",
                    "OpenCodex rejected the shared token. OPENCODEX_API_AUTH_TOKEN must match "
                    "on both Railway services.",
                )
            )
        except GatewayUnavailableError as exc:
            checks.append(
                _check(
                    "ai_veto",
                    "AI brain (OpenCodex)",
                    "fail",
                    f"OpenCodex is not reachable: {exc}",
                )
            )
    return checks


@app.get("/api/preflight")
async def preflight() -> dict[str, Any]:
    """Raw (not enveloped): the frontend renders these checks directly beside Start."""
    checks = await _preflight_checks()
    failed = [check for check in checks if check["status"] == "fail"]
    return {
        "ready": not failed,
        "checks": checks,
        "blocking": [check["id"] for check in failed],
        "observed_at": datetime.now(UTC).isoformat(),
    }


# ---------------------------------------------------------------------------
# 11. Cockpit controls
# ---------------------------------------------------------------------------
@app.get("/api/bot/state")
async def bot_state() -> dict[str, Any]:
    """State machine, autonomy flag, and the measured rolling daily loss."""
    settings = _require(_settings, "settings")
    active_genome = _genome_repo.get_active_genome() if _genome_repo else None
    daily_limit = float(SAFE_DEFAULT_V1.daily_loss_halt * 100)
    if _trading_runtime is None:
        return _env(
            {
                "state": None,
                "full_autonomy": _is_full_autonomy(),
                "autonomy_revoked_reason": _autonomy_state()["revoked_reason"],
                "daily_loss_percent": None,
                "daily_loss_limit": daily_limit,
                "circuit_breaker_tripped": None,
                "active_genome_id": active_genome.genome_id if active_genome else None,
                "canary": _observe_canary(),
            },
            availability="unavailable",
            source="runtime",
            stale=True,
            detail="trading runtime failed to initialise",
        )

    runtime_status = _trading_runtime.status()
    day_start = datetime.now(UTC).replace(hour=0, minute=0, second=0, microsecond=0)
    realized = (
        _ledger_repo.realized_pnl_since(runtime_status.paper_account_id, day_start)
        if _ledger_repo
        else Decimal("0")
    )
    start_balance = settings.paper_starting_balance
    loss_percent = 0.0
    if realized < 0 and start_balance > 0:
        loss_percent = round(float(-realized / start_balance * 100), 2)

    return _env(
        {
            "state": runtime_status.state.value,
            "full_autonomy": _is_full_autonomy(),
            "autonomy_revoked_reason": _autonomy_state()["revoked_reason"],
            "daily_loss_percent": loss_percent,
            "daily_loss_limit": daily_limit,
            "circuit_breaker_tripped": runtime_status.halted,
            "active_genome_id": active_genome.genome_id if active_genome else None,
            "canary": _observe_canary(),
            "paused": runtime_status.paused,
            "has_position": runtime_status.has_position,
            "degraded_reasons": list(runtime_status.degraded_reasons),
        },
        source="runtime",
    )


@app.get("/api/bot/status")
async def bot_status() -> dict[str, Any]:
    """Compact runtime status for the header controls."""
    if _trading_runtime is None:
        return _env(
            {"running": False, "paused": False, "halted": False, "state": None},
            availability="unavailable",
            source="runtime",
            stale=True,
            detail="trading runtime failed to initialise",
        )
    runtime_status = _trading_runtime.status()
    return _env(
        {
            "running": runtime_status.running,
            "paused": runtime_status.paused,
            "halted": runtime_status.halted,
            "state": runtime_status.state.value,
            "market_verified": runtime_status.market_verified,
            "degraded_reasons": list(runtime_status.degraded_reasons),
        },
        source="runtime",
    )


@app.post("/api/bot/start")
async def start_bot() -> dict[str, str]:
    """Arm the paper runtime. Refuses with a readable reason when a gate is not clear."""
    runtime = get_trading_runtime()
    current = runtime.status()
    if current.running and not current.paused:
        return {"status": "already_running"}
    if current.halted:
        raise HTTPException(
            status_code=409,
            detail="paper runtime is halted by emergency stop and requires a deliberate reset",
        )
    blocking = [check for check in await _preflight_checks() if check["status"] == "fail"]
    if blocking:
        raise HTTPException(
            status_code=409,
            detail="; ".join(f"{check['label']}: {check['detail']}" for check in blocking),
        )
    try:
        runtime.start()
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return {"status": "started"}


@app.post("/api/bot/pause")
async def pause_bot() -> dict[str, str]:
    """Stop opening new paper entries while protective monitoring continues."""
    runtime = get_trading_runtime()
    if runtime.status().halted:
        return {"status": "halted"}
    runtime.pause()
    return {"status": "paused"}


@app.post("/api/bot/stop")
async def stop_bot() -> dict[str, str]:
    """Emergency stop: close any paper position, halt mutations, persist the halt."""
    runtime = get_trading_runtime()
    if runtime.status().halted:
        return {"status": "already_stopped"}
    try:
        runtime.stop()
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return {"status": "stopped"}


@app.post("/api/bot/kill-switch")
async def trigger_kill_switch() -> dict[str, str]:
    """Alias of the emergency stop kept for the cockpit's kill-switch control."""
    return await stop_bot()


class AutonomyRevokeRequest(BaseModel):
    """A kill switch needs an auditable reason, so a blank one is rejected at the boundary."""

    reason: Annotated[str, StringConstraints(strip_whitespace=True, min_length=4, max_length=280)]


@app.post("/api/bot/revoke-autonomy")
async def revoke_autonomy(request: AutonomyRevokeRequest) -> dict[str, Any]:
    """Suspend autonomous research and promotion. Durable: it survives a restart."""
    repo = _require(_autonomy_repo, "autonomy store")
    repo.revoke(request.reason)
    logger.info("Autonomy revoked - %s", request.reason)
    return {"status": "autonomy_revoked", "full_autonomy": False, "reason": request.reason}


@app.post("/api/bot/restore-autonomy")
async def restore_autonomy() -> dict[str, Any]:
    """Re-enable autonomous research and promotion. Does not clear an emergency stop."""
    repo = _require(_autonomy_repo, "autonomy store")
    repo.restore()
    logger.info("Autonomy restored")
    return {"status": "autonomy_restored", "full_autonomy": True}


@app.post("/api/bot/revert-baseline")
async def revert_baseline() -> dict[str, Any]:
    """Reinstate the verified baseline genome as the active strategy."""
    repo = _require(_genome_repo, "genome repository")
    baseline = trend_pullback_v1()
    repo.save_genome(baseline, origin="baseline", status="active")
    logger.info("Strategy reverted to baseline: %s", baseline.genome_id)
    return {"status": "reverted_to_baseline", "active_genome_id": baseline.genome_id}


# ---------------------------------------------------------------------------
# 12. Agent activity feed
# ---------------------------------------------------------------------------
@app.get("/api/agent/events")
async def agent_events(limit: int = AGENT_EVENT_DISPLAY_LIMIT) -> dict[str, Any]:
    """Newest agent decisions, bounded to the display cap. Audit history lives in the ledger."""
    if _trading_runtime is None:
        return _env(
            [],
            availability="unavailable",
            source="event-bus",
            stale=True,
            detail="trading runtime failed to initialise",
        )
    bounded = max(1, min(limit, AGENT_EVENT_DISPLAY_LIMIT))
    events = [_event_payload(event) for event in reversed(_trading_runtime.recent_events(bounded))]
    return _env(
        events,
        source="event-bus",
        availability="available" if events else "unavailable",
        detail=None if events else "the agent has not published an event yet",
    )


def _sse(event_name: str, payload: dict[str, Any]) -> str:
    return f"event: {event_name}\ndata: {json.dumps(payload)}\n\n"


async def _agent_event_frames() -> AsyncGenerator[str, None]:
    runtime = _trading_runtime
    if runtime is None:
        yield _sse("snapshot", {"events": [], "bounded_to": AGENT_EVENT_DISPLAY_LIMIT})
        return

    subscription = runtime.subscribe_events()
    pending: asyncio.Task[AgentEvent] | None = asyncio.ensure_future(anext(subscription))
    # Register the queue before snapshotting: an event published during the handshake is
    # then delivered twice rather than lost, and the UI keys on event_id.
    await asyncio.sleep(0)
    try:
        snapshot = [_event_payload(event) for event in reversed(runtime.recent_events())]
        yield _sse("snapshot", {"events": snapshot, "bounded_to": AGENT_EVENT_DISPLAY_LIMIT})
        while True:
            if pending is None:
                pending = asyncio.ensure_future(anext(subscription))
            # asyncio.wait leaves an unfinished task running, so the heartbeat never
            # cancels a pending queue read and never drops an event.
            done, _ = await asyncio.wait({pending}, timeout=SSE_HEARTBEAT_SECONDS)
            if not done:
                yield ": heartbeat\n\n"
                continue
            finished, pending = pending, None
            try:
                event = finished.result()
            except StopAsyncIteration:
                break
            yield _sse("agent_event", _event_payload(event))
    finally:
        if pending is not None:
            pending.cancel()
            with suppress(asyncio.CancelledError, StopAsyncIteration):
                await pending
        with suppress(RuntimeError):
            await subscription.aclose()


@app.get("/api/agent/events/stream")
async def agent_event_stream() -> StreamingResponse:
    """SSE feed: one snapshot frame, then live events, with heartbeats to keep proxies open."""
    return StreamingResponse(
        _agent_event_frames(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-store", "X-Accel-Buffering": "no"},
    )


# ---------------------------------------------------------------------------
# 13. Audit ledger & trade history
# ---------------------------------------------------------------------------
@app.get("/api/decisions")
async def list_decisions(limit: int = 50) -> dict[str, Any]:
    """Decision chains joined to the AI and risk verdicts that produced them."""
    ledger = _require(_ledger_repo, "ledger repository")
    rows = ledger.list_decisions(limit=max(1, min(limit, 500)))
    return _env(
        rows,
        source="decision-ledger",
        availability="available" if rows else "unavailable",
        detail=None if rows else "no closed candle has been evaluated yet",
    )


@app.get("/api/trades")
async def list_trades() -> dict[str, Any]:
    """Durable paper fill history, so restarts do not blank the trade log."""
    ledger = _require(_ledger_repo, "ledger repository")
    account = _paper_account_id()
    fills = ledger.list_order_fills(account) if account else []
    rows = [
        {
            "client_order_id": str(row["client_order_id"]),
            "side": str(row["side"]),
            "status": str(row["status"]),
            "quantity": None if row["quantity_text"] is None else str(row["quantity_text"]),
            "price": None if row["price_text"] is None else str(row["price_text"]),
            "fee": None if row["fee_text"] is None else str(row["fee_text"]),
            "filled_at": None if row["occurred_at"] is None else str(row["occurred_at"]),
        }
        for row in fills
    ]
    return _env(
        rows,
        source="paper-ledger",
        availability="available" if rows else "unavailable",
        detail=None if rows else "no paper order has been filled yet",
    )


# ---------------------------------------------------------------------------
# 14. Sessions & settings
# ---------------------------------------------------------------------------
@app.get("/api/sessions")
async def list_sessions() -> dict[str, Any]:
    """Paper trading sessions."""
    ledger = _require(_ledger_repo, "ledger repository")
    sessions = ledger.list_paper_sessions()
    rows = [
        {
            "id": session.identifier,
            "initial_balance": str(session.initial_balance),
            "created_at": session.created_at,
            "active": session.identifier == _paper_account_id(),
        }
        for session in sessions
    ]
    return _env(rows, source="paper-ledger", availability="available" if rows else "unavailable")


@app.post("/api/sessions")
async def create_session(initial_balance: str = "100") -> dict[str, str]:
    """Open a new paper session."""
    ledger = _require(_ledger_repo, "ledger repository")
    try:
        balance = Decimal(initial_balance)
    except (InvalidOperation, ValueError):
        raise HTTPException(status_code=400, detail="Invalid balance value") from None
    if balance <= 0:
        raise HTTPException(status_code=400, detail="initial balance must be positive")
    session_id = ledger.create_paper_session(balance)
    return {"session_id": session_id, "initial_balance": initial_balance}


@app.get("/api/settings")
async def get_settings() -> dict[str, Any]:
    """Effective configuration. Paper knobs are editable in the app."""
    settings = _require(_settings, "settings")
    return _env(
        _settings_payload(settings),
        source="app-settings",
        detail="Starting balance and risk per trade save here. No Railway restart.",
    )


class SettingsUpdate(BaseModel):
    paper_starting_balance: Decimal | None = Field(default=None, gt=0, le=Decimal("1000000"))
    paper_risk_per_trade: Decimal | None = Field(
        default=None, ge=Decimal("0.0005"), le=Decimal("0.01")
    )


@app.post("/api/settings")
async def update_settings(update: SettingsUpdate) -> dict[str, Any]:
    """Save paper knobs in the app and apply them immediately."""
    global _settings, _risk_engine
    settings = _require(_settings, "settings")
    ledger = _require(_ledger_repo, "ledger repository")
    payload = update.model_dump(exclude_none=True)
    if not payload:
        raise HTTPException(status_code=400, detail="nothing to update")
    next_settings = settings.model_copy(update=payload)
    try:
        risk = strategy_settings_from_app(next_settings)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    stored = {
        "paper_starting_balance": str(next_settings.paper_starting_balance),
        "paper_risk_per_trade": str(next_settings.paper_risk_per_trade),
    }
    ledger.activate_settings("app-v1", stored)
    ledger.append_audit("operator", "settings.update", stored)

    reset_session = (
        "paper_starting_balance" in payload
        and payload["paper_starting_balance"] != settings.paper_starting_balance
    )
    engine = RiskEngine(risk)
    session_id = _paper_account_id()
    if _trading_runtime is not None:
        try:
            session_id = _trading_runtime.apply_knobs(
                next_settings, engine, reset_session=reset_session
            )
        except RuntimeError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
    elif reset_session:
        session_id = ledger.create_paper_session(next_settings.paper_starting_balance)
        if _broker is not None:
            _broker.reset_account(next_settings.paper_starting_balance)

    _settings = next_settings
    _risk_engine = engine
    return _env(
        {**_settings_payload(next_settings), "session_id": session_id},
        source="app-settings",
        detail=(
            "new paper session opened with the saved balance"
            if reset_session
            else "risk settings applied to the current session"
        ),
    )


# ---------------------------------------------------------------------------
# 15. Single-request dashboard snapshot
# ---------------------------------------------------------------------------
_DASHBOARD_SECTIONS: tuple[tuple[str, Callable[[], Awaitable[Any]]], ...] = (
    ("health", health),
    ("status", app_status),
    ("kpi", kpi),
    ("quote", market_quote),
    ("candles", market_candles),
    ("position", position),
    ("equity", equity_curve),
    ("context", live_context),
    ("genomes", list_genomes),
    ("providers", list_providers),
    ("catalog", provider_catalog),
    ("routes", list_routes),
    ("quota", get_quota),
    ("reflections", list_reflections),
    ("botState", bot_state),
    ("agentEvents", agent_events),
    ("preflight", preflight),
    ("promotionCanary", promotion_canary),
)


@app.get("/api/dashboard")
async def dashboard() -> dict[str, Any]:
    """One request replacing the old 14-endpoint poll. A failing section degrades alone."""
    snapshot: dict[str, Any] = {"generated_at": datetime.now(UTC).isoformat()}
    for name, loader in _DASHBOARD_SECTIONS:
        try:
            snapshot[name] = await loader()
        except HTTPException as exc:
            snapshot[name] = _env(
                None,
                availability="unavailable",
                source="server",
                stale=True,
                detail=str(exc.detail),
            )
        except Exception as exc:
            logger.exception("Dashboard section %s failed", name)
            snapshot[name] = _env(
                None,
                availability="unavailable",
                source="server",
                stale=True,
                detail=f"{type(exc).__name__}: {exc}",
            )
    return snapshot


# ---------------------------------------------------------------------------
# 16. Frontend static files
# ---------------------------------------------------------------------------
_possible_dists = [
    Path(__file__).resolve().parents[3] / "frontend" / "dist",
    Path.cwd() / "frontend" / "dist",
    Path("/app/frontend/dist"),
]
_frontend_dist = next(
    (path for path in _possible_dists if (path / "index.html").exists()),
    _possible_dists[0],
)


@app.get("/", response_model=None)
async def serve_index() -> FileResponse | JSONResponse:
    """Serve the built frontend index."""
    index = _frontend_dist / "index.html"
    if index.exists():
        return FileResponse(index, media_type="text/html")
    return JSONResponse(
        {"message": "Frontend not built. Run 'npm run build' in frontend/."},
        status_code=200,
    )


if _frontend_dist.exists():
    app.mount("/", StaticFiles(directory=str(_frontend_dist), html=True), name="frontend")
