import asyncio

import pytest

from app.market.demo import DEMO_SPEC
from app.market.models import Candle, Tick, Timeframe
from app.replay.broker import SimBroker
from app.replay.engine import ReplayManager, ReplaySession, ticks_from_bars

T0 = 1_780_000_020_000 - (1_780_000_020_000 % 60_000)


def tk(ms, bid, spread=0.2):
    return Tick("XAUUSD", ms, bid, round(bid + spread, 2))


def test_broker_fills_sl_tp_and_costs():
    b = SimBroker(contract_size=100, commission_per_lot=7.0, balance=1000)
    b.on_tick(tk(0, 4000.0))
    long = b.market_order("buy", 0.1, sl_distance=2.0, tp_distance=4.0)
    assert long.entry == 4000.2 and long.sl == 3998.2 and long.tp == 4004.2  # buy at ask
    assert long.risk_money == pytest.approx(2.0 * 10 + 0.7)
    assert b.on_tick(tk(1, 4002.0)) == [] and long.profit == pytest.approx(18.0)
    closed = b.on_tick(tk(2, 4004.3))
    assert closed[0].exit_reason == "tp" and closed[0].exit == 4004.2 and closed[0].net == pytest.approx(40 - 0.7)
    short = b.market_order("sell", 0.1, 2.0, 4.0)  # sell at bid 4004.3
    assert short.sl == 4006.3
    closed = b.on_tick(tk(3, 4006.2))  # ask 4006.4 >= SL -> stopped at the ask (gap/spread realistic)
    assert closed[0].exit_reason == "sl" and closed[0].exit == 4006.4 and closed[0].net == pytest.approx(-21.0 - 0.7)
    assert b.balance == pytest.approx(1000 + 39.3 - 21.7)
    with pytest.raises(ValueError):
        b.market_order("hold", 1, None, None)


def test_ticks_from_bars_fallback():
    bar = Candle("XAUUSD", Timeframe.M1, T0, 10.0, 12.0, 9.0, 11.0, max_spread=0.3, closed=True)
    ts = ticks_from_bars([bar], "XAUUSD")
    assert [t.bid for t in ts] == [10.0, 9.0, 12.0, 11.0] and all(t.time_ms < T0 + 60_000 for t in ts)


class FakeHistory:
    """MT5-like source with bars before the start and ticks after it (including a weekend gap)."""

    def __init__(self):
        self.ticks = [tk(T0 + i * 500, 4000 + (i % 40) * 0.1) for i in range(2400)]  # 20 minutes
        gap = T0 + 3 * 86_400_000  # market reopens 3 days later
        self.ticks += [tk(gap + i * 500, 4010 + (i % 10) * 0.1) for i in range(200)]

    async def rates_before(self, symbol, tf, until, count):
        step = tf.ms
        last = until - (until % step) - step
        return [Candle("XAUUSD", tf, last - (count - 1 - i) * step, 4000, 4001, 3999, 4000.5, closed=True)
                for i in range(count)]

    async def ticks_range(self, symbol, a, b):
        return [t for t in self.ticks if a <= t.time_ms < b]

    async def rates_range(self, symbol, tf, a, b):
        return []


def test_session_never_releases_future_data():
    out = []

    async def run():
        s = ReplaySession(FakeHistory(), DEMO_SPEC, T0, out.append)
        await s.load()
        assert all(c.open_time_ms + tf.ms <= T0 for tf in Timeframe for c in s.hub.candles(tf))
        assert s.hub.stats.last_tick is None  # nothing after the start is visible yet
        await s.advance_to(T0 + 90_000)
        assert s.hub.stats.last_tick.time_ms <= s.clock_ms == T0 + 90_000
        assert all(c.open_time_ms <= s.clock_ms for tf in Timeframe for c in s.hub.candles(tf))
        s.analysis.compute()
        assert s.analysis.last["tickTime"] <= s.clock_ms
        # the 1m candle forming right now only contains released ticks
        cur = s.hub.candles(Timeframe.M1)[-1]
        assert not cur.closed and cur.open_time_ms == T0 + 60_000
        # second-by-second development: one more second changes only the forming candle
        n = len(s.hub.candles(Timeframe.M1))
        await s.advance_to(T0 + 91_000)
        assert len(s.hub.candles(Timeframe.M1)) == n
        # weekend gap is skipped instead of waited out
        await s.advance_to(T0 + 21 * 60_000)
        assert any(e["type"] == "gap" for e in s.events)
        assert s.clock_ms >= T0 + 3 * 86_400_000 - 1000

    asyncio.run(run())


def test_session_speed_and_pause():
    clock = [0.0]

    async def run():
        s = ReplaySession(FakeHistory(), DEMO_SPEC, T0, lambda m: None, speed=10, wall=lambda: clock[0])
        await s.load()
        s.set_paused(False)
        clock[0] += 2.0
        await s.step()
        assert s.clock_ms == T0 + 20_000  # 2 s at 10x
        s.set_paused(True)
        clock[0] += 5.0
        await s.step()
        assert s.clock_ms == T0 + 20_000
        await s.jump(60_000)
        assert s.clock_ms == T0 + 80_000

    asyncio.run(run())


def test_manager_demo_replay_end_to_end():
    from app.hub import MarketHub
    from app.market.demo import DemoMarketSource

    async def run():
        hub = MarketHub(DemoMarketSource(seed=1, realtime=False), "XAUUSD", "demo")
        hub.spec = DEMO_SPEC
        sub = hub.subscribe(queue_size=100_000)
        m = ReplayManager(hub, tick_s=0.01)
        await m.command({"type": "replay_start", "startMs": T0, "speed": 60})
        assert m.session and m.session.data_quality == "synthetic"
        await m.command({"type": "replay_control", "action": "resume"})
        await asyncio.sleep(0.3)
        await m.command({"type": "replay_order", "side": "buy", "volume": 0.1, "slDistance": 2, "tpDistance": 4})
        assert len(m.session.broker.positions) == 1
        await m.command({"type": "replay_close", "id": "all"})
        assert len(m.session.broker.trades) == 1
        await m.command({"type": "replay_start", "startMs": 4_000_000_000_000})  # future -> error, no crash
        assert m.session is None and "fortiden" in m.error
        await m.stop()
        types = set()
        while not sub.queue.empty():
            msg = sub.queue.get_nowait()
            types.add(msg["type"] if msg["type"] != "replay" else "replay:" + msg["data"]["type"])
        assert {"replay_state", "replay:tick", "replay:candle", "replay:analysis"} <= types

    asyncio.run(run())
