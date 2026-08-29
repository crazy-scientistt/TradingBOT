from __future__ import annotations

from fastapi import APIRouter
from fastapi.responses import JSONResponse

router = APIRouter(prefix="/api/health", tags=["health"])


@router.get("/live")
def live() -> dict[str, str]:
    """Liveness: the process event loop responds. Never probes slow dependencies."""
    return {"status": "alive"}


@router.get("/ready")
def ready() -> JSONResponse:
    """Readiness: database has been initialised by lifespan. Fail closed otherwise."""
    from goldguard.web import app as app_module

    if app_module._db is None:
        return JSONResponse(
            status_code=503,
            content={
                "status": "not_ready",
                "reason_codes": ["DATABASE_UNINITIALIZED"],
            },
        )
    return JSONResponse(status_code=200, content={"status": "ready"})
