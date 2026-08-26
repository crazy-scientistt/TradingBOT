"""FastAPI application entry point for GoldGuard.

Start with:
    uvicorn goldguard.web.app:app --port 8000
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from goldguard.config import Settings
from goldguard.storage.database import Database
from goldguard.storage.repositories import (
    GenomeRepository,
    LedgerRepository,
    ProviderRepository,
    QuotaRepository,
    ReflectionRepository,
)

logger = logging.getLogger("goldguard.web")

# ---------------------------------------------------------------------------
# Application state (module-level singletons wired during lifespan)
# ---------------------------------------------------------------------------
_settings: Settings | None = None
_db: Database | None = None
_genome_repo: GenomeRepository | None = None
_ledger_repo: LedgerRepository | None = None
_quota_repo: QuotaRepository | None = None
_provider_repo: ProviderRepository | None = None
_reflection_repo: ReflectionRepository | None = None

# Bot loop control
_bot_task: asyncio.Task[None] | None = None
_bot_running: bool = False


def _get_db() -> Database:
    if _db is None:
        raise RuntimeError("Database not initialised")
    return _db


# ---------------------------------------------------------------------------
# Lifespan
# ---------------------------------------------------------------------------
@asynccontextmanager
async def lifespan(app: FastAPI):  # type: ignore[no-untyped-def]
    global _settings, _db, _genome_repo, _ledger_repo
    global _quota_repo, _provider_repo, _reflection_repo

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
    logger.info("Starting GoldGuard — env=%s mode=%s db=%s",
                _settings.environment, _settings.mode, db_path)

    try:
        _db = Database(db_path)
        _db.migrate()

        _genome_repo = GenomeRepository(_db)
        _ledger_repo = LedgerRepository(_db)
        _quota_repo = QuotaRepository(_db)
        _provider_repo = ProviderRepository(_db)
        _reflection_repo = ReflectionRepository(_db)

        # Ensure a paper session exists
        if _ledger_repo.current_paper_session_id() is None:
            session_id = _ledger_repo.create_paper_session(_settings.paper_starting_balance)
            logger.info("Created initial paper session: %s", session_id)
    except Exception as exc:
        logger.error("Database migration error (degraded mode): %s", exc, exc_info=True)

    yield

    # Shutdown: cancel bot loop if running
    global _bot_task, _bot_running
    if _bot_task is not None and not _bot_task.done():
        _bot_running = False
        _bot_task.cancel()
        with contextlib.suppress(asyncio.CancelledError, Exception):
            await _bot_task
    logger.info("GoldGuard shutdown complete")


# ---------------------------------------------------------------------------
# FastAPI app
# ---------------------------------------------------------------------------
app = FastAPI(
    title="GoldGuard",
    description="Autonomous PAXG/USDT paper trading platform",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------------------------------------------------------------------------
# Health & diagnostics
# ---------------------------------------------------------------------------
@app.get("/api/health")
async def health() -> dict[str, Any]:
    """Production health check — verifies DB, quota, and gateway reachability."""
    results: dict[str, Any] = {"status": "ok", "timestamp": datetime.now(UTC).isoformat()}
    if _db is None:
        results["status"] = "starting"
        results["database"] = "uninitialized"
        return results

    try:
        integrity = _db.integrity_check()
        results["database"] = integrity
    except Exception as exc:
        results["database"] = f"FAIL: {exc}"
        results["status"] = "degraded"

    if _quota_repo is not None:
        today = datetime.now(UTC).strftime("%Y-%m-%d")
        bt, wc = _quota_repo.get_usage(today)
        results["quota"] = {"backtests_today": bt, "web_calls_today": wc}

    results["bot_running"] = _bot_running
    return results


@app.get("/api/status")
async def status() -> dict[str, Any]:
    """Overall system status for the dashboard header."""
    assert _settings is not None
    return {
        "environment": _settings.environment,
        "mode": _settings.mode,
        "symbol": _settings.symbol,
        "bot_running": _bot_running,
        "paper_balance": str(_settings.paper_starting_balance),
        "live_enabled": _settings.live_capability_enabled,
    }


# ---------------------------------------------------------------------------
# KPI & dashboard data
# ---------------------------------------------------------------------------
@app.get("/api/kpi")
async def kpi() -> dict[str, Any]:
    """Key performance indicators for the dashboard KPI cards."""
    assert _genome_repo is not None
    assert _ledger_repo is not None

    active = _genome_repo.get_active_genome()
    sessions = _ledger_repo.list_paper_sessions()
    chain_count = _ledger_repo.count_decision_chains()

    return {
        "active_genome": active.genome_id if active else None,
        "total_sessions": len(sessions),
        "decision_chains": chain_count,
        "bot_running": _bot_running,
    }


# ---------------------------------------------------------------------------
# Genomes
# ---------------------------------------------------------------------------
@app.get("/api/genomes")
async def list_genomes(status_filter: str | None = None) -> list[dict[str, Any]]:
    """List strategy genomes, optionally filtered by status."""
    assert _genome_repo is not None
    return _genome_repo.list_genomes(status=status_filter)


@app.get("/api/genomes/{genome_id}")
async def get_genome(genome_id: str) -> dict[str, Any]:
    """Get a specific genome by ID."""
    assert _genome_repo is not None
    row = _genome_repo.get_genome_row(genome_id)
    if row is None:
        raise HTTPException(status_code=404, detail=f"Genome {genome_id} not found")
    return row


# ---------------------------------------------------------------------------
# Provider routes
# ---------------------------------------------------------------------------
@app.get("/api/routes")
async def list_routes() -> dict[str, Any]:
    """Current active model route matrix."""
    assert _provider_repo is not None
    routes = _provider_repo.get_active_routes()
    return {
        role: {
            "provider": r.provider,
            "model": r.model,
            "pinned": r.pinned,
            "version": r.version,
        }
        for role, r in routes.items()
    }


@app.post("/api/routes/{role}")
async def set_route(role: str, provider: str, model: str, pinned: bool = True) -> dict[str, Any]:
    """Set or update a model route for a given role."""
    assert _provider_repo is not None
    version = _provider_repo.set_route(role, provider, model, pinned)
    return {"role": role, "provider": provider, "model": model, "version": version}


# ---------------------------------------------------------------------------
# Reflections (memory)
# ---------------------------------------------------------------------------
@app.get("/api/reflections")
async def list_reflections(namespace: str | None = None, limit: int = 100) -> list[dict[str, Any]]:
    """List trade reflections from memory."""
    assert _reflection_repo is not None
    return _reflection_repo.list_reflections(namespace=namespace, limit=limit)


# ---------------------------------------------------------------------------
# Paper sessions & trades
# ---------------------------------------------------------------------------
@app.get("/api/sessions")
async def list_sessions() -> list[dict[str, Any]]:
    """List all paper trading sessions."""
    assert _ledger_repo is not None
    sessions = _ledger_repo.list_paper_sessions()
    return [
        {
            "id": s.identifier,
            "initial_balance": str(s.initial_balance),
            "created_at": s.created_at,
        }
        for s in sessions
    ]


@app.post("/api/sessions")
async def create_session(initial_balance: str = "100") -> dict[str, str]:
    """Create a new paper trading session."""
    assert _ledger_repo is not None
    try:
        bal = Decimal(initial_balance)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid balance value") from None
    session_id = _ledger_repo.create_paper_session(bal)
    return {"session_id": session_id, "initial_balance": initial_balance}


# ---------------------------------------------------------------------------
# Quota
# ---------------------------------------------------------------------------
@app.get("/api/quota")
async def get_quota() -> dict[str, Any]:
    """Today's research quota usage."""
    assert _quota_repo is not None
    assert _settings is not None
    today = datetime.now(UTC).strftime("%Y-%m-%d")
    bt, wc = _quota_repo.get_usage(today)
    return {
        "date": today,
        "backtests_used": bt,
        "backtests_limit": _settings.research_backtest_max_per_day,
        "web_calls_used": wc,
        "web_calls_limit": _settings.research_web_calls_max_per_day,
    }


# ---------------------------------------------------------------------------
# Bot control
# ---------------------------------------------------------------------------
async def _bot_loop() -> None:
    """Placeholder trading loop — polls Binance and runs coordinator every 15m candle close."""
    global _bot_running
    logger.info("Bot loop started")
    try:
        while _bot_running:
            # In production this would:
            # 1. Poll Binance for closed 15m candles
            # 2. Build FeatureSnapshot from indicator engine
            # 3. Call TradingCoordinator.scan_closed_candle()
            # 4. Monitor open positions via coordinator.monitor_open_position()
            # 5. Run Hermes research loop on schedule
            logger.info("Bot tick — %s", datetime.now(UTC).isoformat())
            await asyncio.sleep(60)
    except asyncio.CancelledError:
        logger.info("Bot loop cancelled")
    finally:
        _bot_running = False
        logger.info("Bot loop stopped")


@app.post("/api/bot/start")
async def start_bot() -> dict[str, str]:
    """Start the autonomous trading loop."""
    global _bot_task, _bot_running
    if _bot_running:
        return {"status": "already_running"}
    _bot_running = True
    _bot_task = asyncio.create_task(_bot_loop())
    return {"status": "started"}


@app.post("/api/bot/stop")
async def stop_bot() -> dict[str, str]:
    """Stop the autonomous trading loop."""
    global _bot_task, _bot_running
    if not _bot_running:
        return {"status": "already_stopped"}
    _bot_running = False
    if _bot_task is not None and not _bot_task.done():
        _bot_task.cancel()
    return {"status": "stopped"}


@app.get("/api/bot/status")
async def bot_status() -> dict[str, Any]:
    """Current bot loop status."""
    return {"running": _bot_running}


# ---------------------------------------------------------------------------
# Audit log
# ---------------------------------------------------------------------------
@app.get("/api/audit")
async def list_audit(limit: int = 50) -> list[dict[str, Any]]:
    """Recent audit events."""
    db = _get_db()
    with db.connect() as conn:
        rows = conn.execute(
            "SELECT * FROM audit_events ORDER BY rowid DESC LIMIT ?",
            (limit,),
        ).fetchall()
    return [dict(r) for r in rows]


# ---------------------------------------------------------------------------
# Frontend static files (served from built frontend dist/)
# ---------------------------------------------------------------------------
_possible_dists = [
    Path(__file__).resolve().parents[3] / "frontend" / "dist",
    Path.cwd() / "frontend" / "dist",
    Path("/app/frontend/dist"),
]
_frontend_dist = next(
    (p for p in _possible_dists if (p / "index.html").exists()),
    _possible_dists[0],
)


@app.get("/", response_model=None)
async def serve_index() -> FileResponse | JSONResponse:
    """Serve frontend index.html."""
    index = _frontend_dist / "index.html"
    if index.exists():
        return FileResponse(index, media_type="text/html")
    return JSONResponse(
        {"message": "Frontend not built. Run 'npm run build' in frontend/."},
        status_code=200,
    )


# Mount static assets AFTER API routes so /api/* takes priority
if _frontend_dist.exists():
    app.mount("/", StaticFiles(directory=str(_frontend_dist), html=True), name="frontend")
