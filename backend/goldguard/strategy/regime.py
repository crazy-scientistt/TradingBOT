from goldguard.strategy.engine import StrategyFeatures


def is_long_regime(features: StrategyFeatures) -> bool:
    return (
        features.ema50_1h > features.ema200_1h
        and features.latest_close_1h > features.ema200_1h
        and features.ema50_slope_1h > 0
    )
