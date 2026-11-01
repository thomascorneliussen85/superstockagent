import asyncio
import math

from app.analysis.engine import analyze, analyze_timeframe, spread_stats, trend_label
from app.analysis.service import AnalysisService
from app.hub import MarketHub
from app.market.demo import DEMO_SPEC, DemoMarketSource
from app.market.models import Tick, Timeframe

from .helpers import bars


def wave_trend(n, slope):
    return [4000 + slope * i + 3 * math.sin(i / 3) for i in range(n)]


def test_uptrend_detected_on_all_votes():
    a = analyze_timeframe(Timeframe.M1, bars(wave_trend(260, 0.5), last_open=True), DEMO_SPEC)
    assert not a["insufficient"]
    assert a["trend"]["label"] == "up"
    assert a["emaStack"] == "bull" and a["aboveEma200"] is True
    assert a["supertrend"]["dir"] == 1
    assert a["ema"]["200"] is not None
    assert a["formingT"] is not None


def test_downtrend_detected():
    a = analyze_timeframe(Timeframe.M5, bars(wave_trend(260, -0.5), tf=Timeframe.M5), DEMO_SPEC)
    assert a["trend"]["label"] == "down"
    assert a["rsi"] is not None and a["rsi"] < 50


def test_insufficient_data_and_missing_ema200():
    assert analyze_timeframe(Timeframe.H1, bars([4000.0] * 10), DEMO_SPEC)["insufficient"]
    a = analyze_timeframe(Timeframe.H1, bars(wave_trend(60, 0.5)), DEMO_SPEC)
    assert a["ema"]["200"] is None and a["aboveEma200"] is None
    assert a["trend"]["votes"]["ema200"] == 0


def test_trend_label_thresholds():
    assert trend_label(2) == "up" and trend_label(-2) == "down" and trend_label(1) == "sideways"


def test_spread_stats():
    s = spread_stats([0.2] * 100, 0.6, DEMO_SPEC)
    assert s["state"] == "high" and s["ratio"] == 3.0
    assert s["costPerLot"] == 60.0  # 0.60 USD x 100 oz
    assert s["points"] == 60
    assert spread_stats([0.2] * 10, 0.2, DEMO_SPEC)["state"] is None  # too few samples


def test_analyze_whole_snapshot():
    c = {tf: bars(wave_trend(250, 0.3), tf=tf) for tf in Timeframe}
    tick = Tick("XAUUSD", 1, 4074.0, 4074.3)
    r = analyze(c, DEMO_SPEC, tick, [0.3] * 100, 123)
    assert set(r["timeframes"]) == {"1m", "5m", "15m", "1h"}
    assert r["alignment"]["up"] == 4
    assert r["spread"]["state"] == "normal"


def test_service_publishes_and_dedupes_events():
    async def run():
        src = DemoMarketSource(seed=5, realtime=False)
        hub = MarketHub(src, "XAUUSD", "demo")
        hub.spec = DEMO_SPEC
        for tf in Timeframe:
            hub.seed_history(tf, await src.history("XAUUSD", tf, 300))
        svc = AnalysisService(hub)
        sub = hub.subscribe()
        svc.tick()
        first = svc.last
        assert first is not None and first["recentEvents"] == []  # history not replayed
        svc.tick()  # no new data -> no new publish
        msgs = []
        while not sub.queue.empty():
            msgs.append(sub.queue.get_nowait())
        assert [m["type"] for m in msgs].count("analysis") == 1
        assert any(m["type"] == "analysis" for m in hub.snapshot())  # retained for new clients

    asyncio.run(run())
