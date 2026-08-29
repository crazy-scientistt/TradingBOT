from __future__ import annotations

import pytest
from goldguard.domain.profile import default_autonomous_profile
from goldguard.exchange.binance_transport import BinanceTransport
from goldguard.live.binance_preflight import BinancePreflight
from pydantic import SecretStr
from tests.exchange.fake_binance import FakeBinance


@pytest.mark.asyncio
async def test_binance_preflight_checks_credentials() -> None:
    profile = default_autonomous_profile()

    transport_empty = BinanceTransport()
    preflight = BinancePreflight(transport_empty)
    report = await preflight.run(profile)
    assert report.ready is False
    assert "MISSING_BINANCE_CREDENTIALS" in report.blockers


@pytest.mark.asyncio
async def test_credentials_without_transport_client_fail_closed() -> None:
    profile = default_autonomous_profile()
    transport = BinanceTransport(api_key=SecretStr("key"), api_secret=SecretStr("secret"))
    report = await BinancePreflight(transport).run(profile)
    assert report.ready is False
    assert "TRANSPORT_UNAVAILABLE" in report.blockers


@pytest.mark.asyncio
async def test_preflight_passes_on_healthy_fake_account() -> None:
    profile = default_autonomous_profile()
    fake = FakeBinance()
    transport = BinanceTransport(
        api_key=SecretStr("key"), api_secret=SecretStr("secret"), client=fake
    )
    report = await BinancePreflight(transport).run(profile)
    assert report.ready is True
    assert report.blockers == ()
    assert report.withdrawals_disabled is True
    assert report.server_time_synced is True


@pytest.mark.asyncio
async def test_preflight_blocks_when_withdrawals_enabled() -> None:
    profile = default_autonomous_profile()
    fake = FakeBinance()
    fake.restrictions["enableWithdrawals"] = True
    transport = BinanceTransport(
        api_key=SecretStr("key"), api_secret=SecretStr("secret"), client=fake
    )
    report = await BinancePreflight(transport).run(profile)
    assert report.ready is False
    assert "WITHDRAWALS_OR_TRANSFERS_ENABLED" in report.blockers
