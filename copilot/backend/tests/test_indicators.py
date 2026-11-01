import pytest

from app.analysis import indicators as ind

# Wilder's RSI example data and published 14-period values (StockCharts "RSI" ChartSchool table).
WILDER = [44.3389, 44.0902, 44.1497, 43.6124, 44.3278, 44.8264, 45.0955, 45.4245, 45.8433, 46.0826,
          45.8931, 46.0328, 45.6140, 46.2820, 46.2820, 46.0028, 46.0328, 46.4116, 46.2222, 45.6439,
          46.2122, 46.2521, 45.7137, 46.4515, 45.7835, 45.3548, 44.0288, 44.1783, 44.2181, 44.5672,
          43.4205, 42.6628, 43.1314]
WILDER_RSI = [70.53, 66.32, 66.55, 69.41, 66.36, 57.97, 62.93, 63.26, 56.06, 62.38, 54.71, 50.42,
              39.99, 41.46, 41.87, 45.46, 37.30, 33.08, 37.77]


def test_rsi_matches_wilder_reference():
    r = ind.rsi(WILDER, 14)
    assert r[:14] == [None] * 14  # first value needs 14 changes
    assert [round(x, 2) for x in r[14:]] == WILDER_RSI


def test_rsi_edge_cases():
    assert ind.rsi([1, 2, 3, 4, 5, 6], 3)[-1] == 100.0
    assert ind.rsi([6, 5, 4, 3, 2, 1], 3)[-1] == 0.0
    assert ind.rsi([5] * 6, 3)[-1] == 50.0


def test_sma_and_ema_hand_calculated():
    v = [1, 2, 3, 4, 5, 6]
    assert ind.sma(v, 3) == [None, None, 2.0, 3.0, 4.0, 5.0]
    e = ind.ema(v, 3)  # alpha 0.5, seeded with SMA(1,2,3)=2
    assert e[:2] == [None, None]
    assert e[2:] == pytest.approx([2.0, 3.0, 4.0, 5.0])
    e2 = ind.ema([10, 10, 10, 20], 3)
    assert e2[-1] == pytest.approx(15.0)


def test_rma_is_wilder_smoothing():
    r = ind.rma([2, 4, 6, 8], 2)  # seed 3, then 0.5*6+0.5*3=4.5, 0.5*8+0.5*4.5=6.25
    assert r == [None, 3.0, 4.5, 6.25]


def test_true_range_and_atr():
    h, l, c = [10, 12, 11], [8, 9, 7], [9, 11, 8]  # noqa: E741
    assert ind.true_range(h, l, c) == [2, 3, 4]  # bar2: max(4, |11-11|, |7-11|)
    assert ind.atr(h, l, c, 2) == [None, 2.5, 3.25]


def test_supertrend_follows_trend_and_flips():
    up = [100 + i for i in range(40)]
    down = [139 - 2 * i for i in range(1, 30)]
    closes = up + down
    highs = [x + 0.5 for x in closes]
    lows = [x - 0.5 for x in closes]
    line, d = ind.supertrend(highs, lows, closes, 3, 10)
    assert d[:9] == [None] * 9
    assert d[39] == 1 and line[39] < closes[39]  # support below price in uptrend
    assert d[-1] == -1 and line[-1] > closes[-1]  # resistance above price in downtrend
    flip = next(i for i in range(40, len(d)) if d[i] == -1)
    assert 40 <= flip < 50


def test_supertrend_band_only_ratchets_in_trend():
    closes = [100 + i for i in range(40)]
    line, d = ind.supertrend([x + 1 for x in closes], [x - 1 for x in closes], closes)
    ups = [v for v, dd in zip(line, d, strict=True) if dd == 1]
    assert all(b >= a for a, b in zip(ups, ups[1:], strict=False))


def test_percentile_rank():
    assert ind.percentile_rank([1, 2, 3, 4], 2) == 50.0
    assert ind.percentile_rank([None, None], 1) is None
