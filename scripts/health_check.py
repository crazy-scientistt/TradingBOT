"""Comprehensive production health check for GoldGuard Autonomous Gold Trader."""

import argparse
import asyncio
import logging
import sys
from datetime import UTC, datetime
from pathlib import Path

import httpx
from goldguard.storage.database import Database
from goldguard.storage.repositories import (
    GenomeRepository,
    ProviderRepository,
    QuotaRepository,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("goldguard.health")


async def check_health(db_path: Path, gateway_url: str) -> dict[str, str]:
    results: dict[str, str] = {}

    # 1. Database Check
    try:
        db = Database(db_path)
        db.migrate()
        genome_repo = GenomeRepository(db)
        quota_repo = QuotaRepository(db)
        prov_repo = ProviderRepository(db)

        active = genome_repo.get_active_genome()
        today = datetime.now(UTC).strftime("%Y-%m-%d")
        quota = quota_repo.get_usage(today)
        routes = prov_repo.get_active_routes()

        results["database"] = f"OK (active_genome: {active.genome_id if active else 'None'})"
        results["quota"] = f"OK (backtests: {quota[0]}, web_calls: {quota[1]})"
        results["routes"] = f"OK (configured_roles: {list(routes.keys())})"
    except Exception as exc:
        results["database"] = f"FAIL ({exc})"
        results["quota"] = "FAIL"
        results["routes"] = "FAIL"

    # 2. OpenCodex Gateway Check
    try:
        async with httpx.AsyncClient(timeout=3.0) as client:
            resp = await client.get(f"{gateway_url}/healthz")
            if resp.status_code == 200:
                results["gateway"] = "OK (200 OK)"
            else:
                results["gateway"] = f"DEGRADED ({resp.status_code})"
    except Exception:
        results["gateway"] = "UNREACHABLE (local fallback active)"

    return results


def main() -> int:
    parser = argparse.ArgumentParser(description="GoldGuard Health Check")
    parser.add_argument("--db", default="data/goldguard.db", help="Path to SQLite database")
    parser.add_argument(
        "--gateway-url", default="http://localhost:10100", help="OpenCodex Gateway URL"
    )
    args = parser.parse_args()

    results = asyncio.run(check_health(Path(args.db), args.gateway_url))
    logger.info("=== GoldGuard Production System Health ===")
    all_ok = True
    for component, status in results.items():
        logger.info("  [%s]: %s", component.upper(), status)
        if status.startswith("FAIL"):
            all_ok = False

    return 0 if all_ok else 1


if __name__ == "__main__":
    sys.exit(main())
