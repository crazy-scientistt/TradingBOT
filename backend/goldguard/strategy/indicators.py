from statistics import median


def ema_series(values: list[float], period: int) -> list[float]:
    if period <= 0:
        raise ValueError("EMA period must be positive")
    if not values:
        return []
    alpha = 2.0 / (period + 1.0)
    result = [values[0]]
    for value in values[1:]:
        result.append((alpha * value) + ((1.0 - alpha) * result[-1]))
    return result


def wilder_average(values: list[float], period: int) -> list[float | None]:
    if period <= 0:
        raise ValueError("Wilder period must be positive")
    result: list[float | None] = [None] * len(values)
    if len(values) < period:
        return result
    current = sum(values[:period]) / period
    result[period - 1] = current
    for index in range(period, len(values)):
        current = ((current * (period - 1)) + values[index]) / period
        result[index] = current
    return result


def rsi_wilder(closes: list[float], period: int = 14) -> list[float | None]:
    result: list[float | None] = [None] * len(closes)
    if len(closes) <= period:
        return result
    changes = [closes[index] - closes[index - 1] for index in range(1, len(closes))]
    gains = [max(change, 0.0) for change in changes]
    losses = [max(-change, 0.0) for change in changes]
    average_gain = sum(gains[:period]) / period
    average_loss = sum(losses[:period]) / period

    def calculate(gain: float, loss: float) -> float:
        if gain == 0 and loss == 0:
            return 50.0
        if loss == 0:
            return 100.0
        relative_strength = gain / loss
        return 100.0 - (100.0 / (1.0 + relative_strength))

    result[period] = calculate(average_gain, average_loss)
    for change_index in range(period, len(changes)):
        average_gain = ((average_gain * (period - 1)) + gains[change_index]) / period
        average_loss = ((average_loss * (period - 1)) + losses[change_index]) / period
        result[change_index + 1] = calculate(average_gain, average_loss)
    return result


def true_ranges(highs: list[float], lows: list[float], closes: list[float]) -> list[float]:
    if not (len(highs) == len(lows) == len(closes)):
        raise ValueError("high, low, and close series must be the same length")
    result: list[float] = []
    for index, (high, low) in enumerate(zip(highs, lows, strict=True)):
        if high < low:
            raise ValueError("high cannot be below low")
        if index == 0:
            result.append(high - low)
            continue
        previous_close = closes[index - 1]
        result.append(max(high - low, abs(high - previous_close), abs(low - previous_close)))
    return result


def atr_wilder(
    highs: list[float],
    lows: list[float],
    closes: list[float],
    period: int = 14,
) -> list[float | None]:
    return wilder_average(true_ranges(highs, lows, closes), period)


def median_volume_ratio(volumes: list[float], lookback: int = 20) -> float:
    if lookback <= 0 or len(volumes) < lookback:
        raise ValueError("insufficient volume history")
    sample = volumes[-lookback:]
    baseline = median(sample)
    if baseline <= 0:
        return 0.0
    return sample[-1] / baseline
