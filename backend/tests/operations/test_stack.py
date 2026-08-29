from __future__ import annotations

from goldguard.config import Settings
from goldguard.operations.stack import REQUIRED_CHECKS, collect_stack_diagnostics


def test_unconfigured_gateway_is_a_named_blocker() -> None:
    settings = Settings(
        gateway_base_url=None,
        gateway_data_token=None,
        hermes_base_url=None,
        hermes_bridge_token=None,
        market_ingestion_enabled=False,
    )

    async def _run() -> None:
        report = await collect_stack_diagnostics(
            settings=settings,
            database_ready=True,
            paper_broker_ready=True,
        )
        names = {item["name"] for item in report["checks"]}
        assert names == set(REQUIRED_CHECKS)
        assert "OPENCODEX_UNCONFIGURED" in report["blockers"]
        assert "HERMES_UNCONFIGURED" in report["blockers"]
        assert report["live_armed"] is False
        assert report["real_orders_placed"] == 0
        opencodex = next(item for item in report["checks"] if item["name"] == "opencodex_model")
        assert opencodex["status"] == "fail"

    import asyncio

    asyncio.run(_run())
