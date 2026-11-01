"""Deterministic technical indicators.

Definitions follow TradingView's Pine built-ins so values can be compared
directly with the chart:

* ``ema``: alpha = 2/(n+1), seeded with the SMA of the first n values (ta.ema)
* ``rma``: Wilder's smoothing, alpha = 1/n, SMA seed (ta.rma)
* ``rsi``: RMA of gains/losses (ta.rsi)
* ``atr``: RMA of true range (ta.atr)
* ``supertrend``: ta.supertrend(factor, atrPeriod) on hl2

All functions take plain lists and return lists of the same length with
``None`` where there is not enough data yet. Pure Python: a few hundred bars
per timeframe is far below where vectorisation matters, and it keeps the
Windows install free of compiled dependencies.
"""

from __future__ import annotations

from collections.abc import Sequence

Series = list[float | None]


def sma(values: Sequence[float], n: int) -> Series:
    out: Series = [None] * len(values)
    if n <= 0:
        raise ValueError("n must be positive")
    s = 0.0
    for i, v in enumerate(values):
        s += v
        if i >= n:
            s -= values[i - n]
        if i >= n - 1:
            out[i] = s / n
    return out


def _smooth(values: Sequence[float | None], n: int, alpha: float) -> Series:
    """Exponential smoothing seeded by the SMA of the first n non-None values."""
    out: Series = [None] * len(values)
    seed: list[float] = []
    prev: float | None = None
    for i, v in enumerate(values):
        if v is None:
            continue
        if prev is None:
            seed.append(v)
            if len(seed) == n:
                prev = sum(seed) / n
                out[i] = prev
            continue
        prev = alpha * v + (1 - alpha) * prev
        out[i] = prev
    return out


def ema(values: Sequence[float | None], n: int) -> Series:
    return _smooth(values, n, 2 / (n + 1))


def rma(values: Sequence[float | None], n: int) -> Series:
    return _smooth(values, n, 1 / n)


def rsi(closes: Sequence[float], n: int = 14) -> Series:
    if len(closes) < 2:
        return [None] * len(closes)
    gains: list[float | None] = [None]
    losses: list[float | None] = [None]
    for i in range(1, len(closes)):
        ch = closes[i] - closes[i - 1]
        gains.append(max(ch, 0.0))
        losses.append(max(-ch, 0.0))
    up = rma(gains, n)
    down = rma(losses, n)
    out: Series = [None] * len(closes)
    for i, (u, d) in enumerate(zip(up, down, strict=True)):
        if u is None or d is None:
            continue
        if d == 0:
            out[i] = 100.0 if u > 0 else 50.0
        elif u == 0:
            out[i] = 0.0
        else:
            out[i] = 100 - 100 / (1 + u / d)
    return out


def true_range(highs: Sequence[float], lows: Sequence[float], closes: Sequence[float]) -> list[float]:
    out: list[float] = []
    for i in range(len(highs)):
        if i == 0:
            out.append(highs[0] - lows[0])
        else:
            pc = closes[i - 1]
            out.append(max(highs[i] - lows[i], abs(highs[i] - pc), abs(lows[i] - pc)))
    return out


def atr(highs: Sequence[float], lows: Sequence[float], closes: Sequence[float], n: int = 14) -> Series:
    return rma(true_range(highs, lows, closes), n)


def supertrend(
    highs: Sequence[float],
    lows: Sequence[float],
    closes: Sequence[float],
    factor: float = 3.0,
    period: int = 10,
) -> tuple[Series, list[int | None]]:
    """Returns (line, direction) with direction +1 = uptrend, -1 = downtrend.

    Note: Pine's ``ta.supertrend`` uses -1 for uptrend; we flip the sign so
    that +1 consistently means bullish in this code base.
    """
    a = atr(highs, lows, closes, period)
    n = len(closes)
    line: Series = [None] * n
    direction: list[int | None] = [None] * n
    prev_upper = prev_lower = 0.0
    prev_st: float | None = None
    prev_atr: float | None = None
    for i in range(n):
        if a[i] is None:
            prev_atr = a[i]
            continue
        src = (highs[i] + lows[i]) / 2
        upper = src + factor * a[i]
        lower = src - factor * a[i]
        pc = closes[i - 1] if i > 0 else closes[i]
        lower = lower if (lower > prev_lower or pc < prev_lower) else prev_lower
        upper = upper if (upper < prev_upper or pc > prev_upper) else prev_upper
        if prev_atr is None:
            pine_dir = 1  # Pine: downtrend until proven otherwise
        elif prev_st == prev_upper:
            pine_dir = -1 if closes[i] > upper else 1
        else:
            pine_dir = 1 if closes[i] < lower else -1
        st = lower if pine_dir == -1 else upper
        line[i] = st
        direction[i] = -pine_dir
        prev_upper, prev_lower, prev_st, prev_atr = upper, lower, st, a[i]
    return line, direction


def percentile_rank(values: Sequence[float | None], value: float) -> float | None:
    """Share (0-100) of non-None ``values`` that are <= ``value``."""
    vals = [v for v in values if v is not None]
    if not vals:
        return None
    return 100.0 * sum(1 for v in vals if v <= value) / len(vals)
