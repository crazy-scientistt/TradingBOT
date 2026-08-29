from __future__ import annotations

import pytest
from goldguard.domain.profile import default_autonomous_profile
from goldguard.exchange.binance_transport import BinanceTransport
from goldguard.live.binance_preflight import BinancePreflight
from pydantic import SecretStr


@pytest.mark.asyncio
async def test_binance_preflight_checks_credentials() -> None:
    profile = default_autonomous_profile()

    # Missing creds
    transport_empty = BinanceTransport()
    preflight = BinancePreflight(transport_empty)
    report = await preflight.run(profile)
    assert report.ready is False
    assert "MISSING_BINANCE_CREDENTIALS" in report.blockers

    # With creds
    transport_ready = BinanceTransport(
        api_key=SecretStr("key"), api_secret=SecretStr("secret")
    )
    preflight_ready = BinancePreflight(transport_ready)
    report_ready = await preflight_ready.run(profile)
    assert report_ready.ready is True
    assert len(report_ready.blockers) == 0

