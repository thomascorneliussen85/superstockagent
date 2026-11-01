from app.analysis.structure import (
    Swing,
    classify_structure,
    cluster_levels,
    detect_patterns,
    find_swings,
    level_events,
    nearest_levels,
    structure_break,
)

from .helpers import bars, candle


def test_swings_need_confirmation_bars():
    closes = [10, 11, 12, 15, 12, 11, 10]
    sw = find_swings(bars(closes, spread=0), left=3, right=3)
    assert [(s.kind, s.price) for s in sw] == [("high", 15)]
    # Without 3 bars after the peak it is not (yet) a swing: no look-ahead.
    assert find_swings(bars(closes[:6], spread=0), 3, 3) == []


def test_structure_classification():
    def s(kind, p, i):
        return Swing(i, i, p, kind)

    up = [s("low", 1, 0), s("high", 5, 1), s("low", 2, 2), s("high", 6, 3)]
    assert classify_structure(up)["label"] == "bullish"
    down = [s("high", 6, 0), s("low", 2, 1), s("high", 5, 2), s("low", 1, 3)]
    assert classify_structure(down)["label"] == "bearish"
    rng = [s("high", 6, 0), s("low", 1, 1), s("high", 5, 2), s("low", 2, 3)]
    assert classify_structure(rng)["label"] == "range"
    assert classify_structure([])["label"] == "unknown"


def test_level_clustering_and_nearest():
    sw = [Swing(0, 0, 100.0, "high"), Swing(1, 1, 100.2, "high"), Swing(2, 2, 95.0, "low"),
          Swing(3, 3, 105.0, "low")]
    levels = cluster_levels(sw, tolerance=0.5)
    assert len(levels) == 3
    eq = next(lv for lv in levels if lv.touches == 2)
    assert abs(eq.price - 100.1) < 1e-9 and eq.highs == 2
    sup, res = nearest_levels(levels, 101)
    assert [round(lv.price, 1) for lv in sup] == [100.1, 95.0]
    assert [lv.price for lv in res] == [105.0]


def test_patterns():
    assert "bullish_engulfing" in detect_patterns([candle(10, 10.2, 8.8, 9), candle(8.9, 10.6, 8.8, 10.5, 1)], None)
    assert "bearish_engulfing" in detect_patterns([candle(9, 10.1, 8.9, 10), candle(10.1, 10.2, 8.5, 8.6, 1)], None)
    assert "bullish_pin" in detect_patterns([candle(10, 11, 9, 10), candle(10, 10.15, 8, 10.1, 1)], None)
    assert "bearish_pin" in detect_patterns([candle(10, 11, 9, 10), candle(10, 12, 9.9, 9.95, 1)], None)
    assert "doji" in detect_patterns([candle(10, 11, 9, 10), candle(10, 10.5, 9.5, 10.01, 1)], None)
    assert "inside_bar" in detect_patterns([candle(10, 12, 8, 11), candle(10, 11, 9, 10.5, 1)], None)
    # Tiny candles relative to ATR are not called pin bars
    assert "bullish_pin" not in detect_patterns([candle(10, 11, 9, 10), candle(10, 10.015, 9.8, 10.01, 1)], 5)


def test_breakout_and_false_breakout():
    from app.analysis.structure import Level

    lv = [Level(100.0, 2, 2, 0, 0)]
    assert level_events([candle(99, 99.5, 98.5, 99.5), candle(99.5, 101, 99.4, 100.8, 1)], lv, 2)[0]["type"] == "breakout_up"
    sweep = level_events([candle(99, 99.5, 98.5, 99.5), candle(99.5, 100.6, 99.2, 99.6, 1)], lv, 2)
    assert sweep[0]["type"] == "false_breakout_up"
    assert level_events([candle(101, 101.5, 100.5, 101), candle(101, 101.2, 99.4, 100.4, 1)], lv, 2)[0]["type"] == "false_breakout_down"


def test_structure_break():
    st = {"lastHigh": 100.0, "lastLow": 90.0}
    assert structure_break([candle(99, 99.5, 98, 99), candle(99, 101, 98.9, 100.5, 1)], st)["type"] == "bos_up"
    assert structure_break([candle(91, 92, 90.5, 91), candle(91, 91, 89, 89.5, 1)], st)["type"] == "bos_down"
    assert structure_break([candle(95, 96, 94, 95), candle(95, 96, 94, 95.5, 1)], st) is None


def test_trendlines_rising_support_and_broken():
    from app.analysis.structure import trendlines

    # zig-zag uptrend: higher lows at i=5 (100) and i=15 (102)
    closes = []
    for i in range(30):
        base = 100 + i * 0.2
        closes.append(base + (2 if i % 10 >= 5 else 0) - (1 if i % 10 == 5 else 0))
    cs = bars(closes, spread=0.2)
    sw = find_swings(cs, 3, 3)
    lines = trendlines(cs, sw, atr=1.0, digits=2)
    sup = [x for x in lines if x["kind"] == "support"]
    assert sup and sup[0]["p2"] > sup[0]["p1"] and sup[0]["t2"] > sup[0]["t1"]
    assert sup[0]["broken"] is False
    crash = cs + bars([90.0], spread=0.2, start=cs[-1].open_time_ms + 60_000)
    again = trendlines(crash, sw, atr=1.0, digits=2)
    assert [x for x in again if x["kind"] == "support"][0]["broken"] is True


def test_volume_profile_poc_and_value_area():
    from app.analysis.structure import volume_profile

    cs = [candle(100, 101, 99, 100, i) for i in range(20)]  # heavy trade around 99-101
    cs += [candle(105, 106, 104, 105, 20 + i) for i in range(3)]
    for c in cs[:20]:
        c.tick_count = 100
    for c in cs[20:]:
        c.tick_count = 10
    vp = volume_profile(cs, 0.5, 2)
    assert 99 <= vp["poc"] <= 101
    assert vp["val"] <= vp["poc"] <= vp["vah"] and vp["vah"] <= 101.5
    assert max(b["v"] for b in vp["bins"]) == 1.0
    assert volume_profile([], 0.5, 2) is None
