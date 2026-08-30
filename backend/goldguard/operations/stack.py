from __future__ import annotations

from typing import Any
from urllib.parse import urlparse

import httpx

from goldguard.config import Settings

REQUIRED_CHECKS = (
    "binance_public",
    "paper_spot",
    "paper_futures",
    "opencodex_model",
    "hermes_http",
    "hermes_proposal",
    "hermes_memory_restart",
    "dataset_verified",
    "reflection_persist",
    "promotion_rollback",
    "telegram_test",
    "database_restart",
    "backup_restore",
    "frontend_truthfulness",
)


def _host_only(url: str | None) -> str | None:
    if not url:
        return None
    parsed = urlparse(url)
    host = parsed.hostname or url
    port = f":{parsed.port}" if parsed.port else ""
    return f"{host}{port}"


def _check(name: str, status: str, detail: str) -> dict[str, str]:
    return {"name": name, "status": status, "detail": detail}


async def probe_http(
    client: httpx.AsyncClient,
    url: str,
    *,
    headers: dict[str, str] | None = None,
    timeout: float = 3.0,
) -> tuple[bool, str]:
    """Return (ok, detail). Never includes the URL or secrets in detail."""
    try:
        response = await client.get(url, headers=headers, timeout=timeout)
    except httpx.TimeoutException:
        return False, "TIMEOUT"
    except httpx.NetworkError:
        return False, "UNREACHABLE"
    except Exception as exc:
        return False, type(exc).__name__
    if response.status_code < 500:
        return True, f"HTTP_{response.status_code}"
    return False, f"HTTP_{response.status_code}"


async def collect_stack_diagnostics(
    *,
    settings: Settings,
    database_ready: bool,
    paper_broker_ready: bool,
    paper_futures_ready: bool | None = None,
    http_client: httpx.AsyncClient | None = None,
    dataset_status: str = "UNKNOWN",
    reflection_count: int | None = None,
    hermes_proposal_ok: bool | None = None,
) -> dict[str, Any]:
    """Honest local/Railway stack report. Missing probes stay failed, never auto-pass."""

    own_client = http_client is None
    client = http_client or httpx.AsyncClient()
    checks: list[dict[str, str]] = []
    blockers: list[str] = []

    try:
        if database_ready:
            checks.append(_check("database_restart", "pass", "initialized"))
        else:
            checks.append(_check("database_restart", "fail", "DATABASE_UNINITIALIZED"))
            blockers.append("DATABASE_UNINITIALIZED")

        futures_ready = paper_broker_ready if paper_futures_ready is None else paper_futures_ready
        if paper_broker_ready:
            checks.append(_check("paper_spot", "pass", "paper broker ready"))
        else:
            checks.append(_check("paper_spot", "fail", "PAPER_BROKER_UNINITIALIZED"))
            blockers.append("PAPER_BROKER_UNINITIALIZED")
        if futures_ready:
            checks.append(_check("paper_futures", "pass", "paper futures adapter present"))
        else:
            checks.append(_check("paper_futures", "fail", "PAPER_FUTURES_UNINITIALIZED"))

        market_base = settings.market_base_url.rstrip("/")
        if settings.market_ingestion_enabled:
            ok, detail = await probe_http(
                client, f"{market_base}/api/v3/ping", timeout=5.0
            )
            if ok:
                checks.append(_check("binance_public", "pass", detail))
            else:
                checks.append(_check("binance_public", "fail", f"BINANCE_PUBLIC_{detail}"))
                blockers.append("BINANCE_PUBLIC_UNREACHABLE")
        else:
            checks.append(_check("binance_public", "not_run", "MARKET_INGESTION_DISABLED"))

        gateway_url = settings.gateway_base_url
        if not gateway_url or not settings.gateway_data_token:
            checks.append(_check("opencodex_model", "fail", "OPENCODEX_UNCONFIGURED"))
            blockers.append("OPENCODEX_UNCONFIGURED")
        else:
            token = settings.gateway_data_token.get_secret_value()
            headers = {
                "x-opencodex-api-key": token,
                "authorization": f"Bearer {token}",
            }
            ok, detail = await probe_http(
                client, f"{gateway_url.rstrip('/')}/healthz", headers=headers
            )
            if ok:
                checks.append(_check("opencodex_model", "pass", detail))
            else:
                checks.append(_check("opencodex_model", "fail", f"OPENCODEX_{detail}"))
                blockers.append("OPENCODEX_UNREACHABLE")

        hermes_url = settings.hermes_base_url
        if not hermes_url or not settings.hermes_bridge_token:
            checks.append(_check("hermes_http", "fail", "HERMES_UNCONFIGURED"))
            checks.append(_check("hermes_memory_restart", "fail", "HERMES_UNCONFIGURED"))
            blockers.append("HERMES_UNCONFIGURED")
        else:
            token = settings.hermes_bridge_token.get_secret_value()
            headers = {"authorization": f"Bearer {token}"}
            ok = False
            detail = "UNREACHABLE"
            for path in ("/health", "/v1/health", "/healthz"):
                ok, detail = await probe_http(
                    client, f"{hermes_url.rstrip('/')}{path}", headers=headers
                )
                if ok:
                    break
            if ok:
                checks.append(_check("hermes_http", "pass", detail))
                if reflection_count and reflection_count > 0:
                    checks.append(
                        _check(
                            "hermes_memory_restart",
                            "pass",
                            "goldguard reflections persisted",
                        )
                    )
                else:
                    checks.append(
                        _check(
                            "hermes_memory_restart",
                            "not_run",
                            "HTTP health is not memory or learning proof",
                        )
                    )
            else:
                checks.append(_check("hermes_http", "fail", f"HERMES_{detail}"))
                checks.append(_check("hermes_memory_restart", "fail", f"HERMES_{detail}"))
                blockers.append("HERMES_UNREACHABLE")

        if hermes_proposal_ok is True:
            checks.append(_check("hermes_proposal", "pass", "authenticated proposal round trip"))
        elif hermes_proposal_ok is False:
            checks.append(_check("hermes_proposal", "fail", "HERMES_PROPOSAL_FAILED"))
            blockers.append("HERMES_PROPOSAL_FAILED")
        else:
            checks.append(
            _check("hermes_proposal", "not_run", "awaiting Hermes proposal round trip")
        )

        if str(dataset_status) == "VERIFIED":
            checks.append(_check("dataset_verified", "pass", "VERIFIED"))
        else:
            checks.append(_check("dataset_verified", "fail", str(dataset_status)))
            if str(dataset_status) in {"CORRUPT", "DOWNLOADING", "UNKNOWN"}:
                blockers.append("DATASET_NOT_VERIFIED")

        if reflection_count is None or reflection_count == 0:
            checks.append(_check("reflection_persist", "not_run", "awaiting closed paper trade"))
        else:
            checks.append(
                _check("reflection_persist", "pass", f"reflections={reflection_count}")
            )

        checks.append(
            _check("promotion_rollback", "not_run", "awaiting paper qualification")
        )
        checks.append(
            _check("telegram_test", "not_run", "operator telegram bot not required for paper")
        )
        checks.append(
            _check(
                "backup_restore",
                "not_run",
                "run scripts/backup_state.py during qualification",
            )
        )
        checks.append(_check("frontend_truthfulness", "not_run", "ui suite is operator-recorded"))
    finally:
        if own_client:
            await client.aclose()

    named = {item["name"] for item in checks}
    for required in REQUIRED_CHECKS:
        if required not in named:
            checks.append(_check(required, "fail", f"{required.upper()}_NOT_READY"))
            blockers.append(f"{required.upper()}_NOT_READY")

    return {
        "blockers": blockers,
        "checks": checks,
        "live_armed": bool(settings.live_capability_enabled and settings.mode == "live"),
        "real_orders_placed": 0,
        "mode": settings.mode,
        "opencodex_host": _host_only(settings.gateway_base_url),
        "hermes_host": _host_only(settings.hermes_base_url),
    }
