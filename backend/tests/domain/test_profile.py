from goldguard.domain.profile import AutonomousProfile


def test_profile_applies_one_risk_envelope_to_paper_and_live() -> None:
    profile = AutonomousProfile.model_validate(
        {
            "execution_mode": "paper",
            "strategy_mode": "autonomous",
            "autonomous_profile": "micro_trade",
            "spot_enabled": True,
            "futures_enabled": True,
            "spot_pairs": ["PAXGUSDT"],
            "futures_pairs": ["BTCUSDT", "ETHUSDT"],
            "risk": {
                "max_capital_per_trade_rate": "0.005",
                "max_futures_leverage": 5,
                "max_total_exposure_rate": "0.20",
                "rolling_24h_loss_limit_rate": "0.03",
            },
        }
    )
    assert profile.risk.max_futures_leverage == 5
    assert profile.spot_pairs == ("PAXGUSDT",)
