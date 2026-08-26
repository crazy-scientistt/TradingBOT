from math import isclose

from goldguard.strategy.indicators import ema_series, rsi_wilder, wilder_average


def test_ema_uses_previous_value_without_future_samples() -> None:
    assert ema_series([10.0, 11.0, 12.0], period=3) == [10.0, 10.5, 11.25]
    assert ema_series([10.0, 11.0], period=3) == [10.0, 10.5]


def test_wilder_rsi_matches_hand_calculated_sequence() -> None:
    result = rsi_wilder([1.0, 2.0, 3.0, 2.0, 3.0], period=3)

    assert result[:3] == [None, None, None]
    assert isclose(result[3] or 0, 66.6666666667, rel_tol=1e-9)
    assert isclose(result[4] or 0, 77.7777777778, rel_tol=1e-9)


def test_wilder_average_seeds_with_simple_average_then_smooths() -> None:
    result = wilder_average([2.0, 3.0, 4.0, 5.0], period=3)

    assert result[:2] == [None, None]
    assert result[2] == 3.0
    assert isclose(result[3] or 0, 3.6666666667, rel_tol=1e-9)
