import importlib
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

from goldguard.domain.models import Candle, Quote

START = datetime(2026, 8, 26, 12, 0, tzinfo=UTC)


def make_closed_candle() -> Candle:
    open_time = START
    close_time = open_time + timedelta(minutes=15)
    return Candle(
        symbol="PAXGUSDT",
        timeframe="15m",
        open_time=open_time,
        close_time=close_time,
        open=Decimal("2500.00"),
        high=Decimal("2506.00"),
        low=Decimal("2498.00"),
        close=Decimal("2504.00"),
        volume=Decimal("12.5"),
        closed=True,
    )


def test_web_runtime_processes_closed_candle_once_and_persists_one_decision_chain(
    tmp_path,
    monkeypatch,
) -> None:
    monkeypatch.setenv("GOLDGUARD_ENVIRONMENT", "test")
    monkeypatch.setenv("GOLDGUARD_DATA_DIR", str(tmp_path))

    import goldguard.web.app as web_module

    web_app = importlib.reload(web_module)
    candle = make_closed_candle()
    quote = Quote(
        bid=Decimal("2503.80"),
        ask=Decimal("2504.00"),
        observed_at=candle.close_time,
    )

    with TestClient(web_app.app):
        runtime = web_app.get_trading_runtime()
        runtime.start()

        outcome = runtime.process_closed_candle(candle, quote)

        assert outcome.action
        assert web_app._ledger_repo is not None
        assert web_app._ledger_repo.count_decision_chains() == 1


def test_web_runtime_preserves_halted_flag_across_process_restart(
    tmp_path,
    monkeypatch,
) -> None:
    monkeypatch.setenv("GOLDGUARD_ENVIRONMENT", "test")
    monkeypatch.setenv("GOLDGUARD_DATA_DIR", str(tmp_path))

    import goldguard.web.app as web_module

    first_app = importlib.reload(web_module)
    with TestClient(first_app.app):
        runtime = first_app.get_trading_runtime()
        runtime.start()
        runtime.stop()
        assert runtime.status().halted is True

    restarted_app = importlib.reload(web_module)
    with TestClient(restarted_app.app):
        runtime = restarted_app.get_trading_runtime()
        assert runtime.status().halted is True
        with pytest.raises(RuntimeError, match="halted"):
            runtime.start()
