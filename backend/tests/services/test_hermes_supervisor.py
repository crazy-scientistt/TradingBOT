from __future__ import annotations

import pytest
from goldguard.services.hermes_supervisor import HermesSupervisor


@pytest.mark.asyncio
async def test_hermes_supervisor_quota_handling() -> None:
    supervisor = HermesSupervisor()
    res_ok = await supervisor.tick()
    assert res_ok.code == "SUCCESS"

    supervisor.consume_all_daily_iterations()
    res_exhausted = await supervisor.tick()
    assert res_exhausted.code == "QUOTA_EXHAUSTED"

