"""Phase 8: realistic trading simulations and long-running stability."""

import asyncio
import random
import time
import tracemalloc

import pytest

from app.analysis.service import AnalysisService
from app.hub import HISTORY_LEN, SPREAD_WINDOW, MarketHub
from app.market.demo import DEMO_SPEC, DemoMarketSource, DemoTickGenerator
from app.market.models import Timeframe
from app.replay.broker import SimBroker
from app.replay.engine import ReplaySession

T0 = 1_780_000_000_000 - (1_780_000_000_000 % 60_000)


def test_strategy_simulation_accounting_invariants():
    """An EMA-cross scalper over one synthetic day: the simulated broker must keep
    exact books and realistic fills."""

    async def run():
        s = ReplaySession(DemoMarketSource(), DEMO_SPEC, T0, lambda m: None)
        s.broker = SimBroker(contract_size=100, commission_per_lot=7.0, balance=10_000)
        await s.load()
        rng = random.Random(1)
        clock = T0
        for _ in range(6 * 60):  # 6 hours, minute by minute
            clock += 60_000
            await s.advance_to(clock)
            s.analysis.compute()
            a = s.analysis.last["timeframes"]["1m"]
            if s.broker.positions or a.get("insufficient"):
                continue
            stack = a.get("emaStack")
            if stack in ("bull", "bear") and rng.random() < 0.3:
                s.broker.market_order("buy" if stack == "bull" else "sell", 0.1, 2.0, 3.0)
        s.broker.close_all()
        b = s.broker
        assert len(b.trades) >= 10
        assert b.balance == pytest.approx(10_000 + sum(t.net for t in b.trades), abs=0.05)
        for t in b.trades:
            assert t.open_ms <= t.close_ms
            assert t.commission == pytest.approx(-0.7)
            if t.exit_reason == "tp":  # limit order: exactly at TP
                assert t.exit == t.tp
            if t.exit_reason == "sl":  # stop at market: never better than the stop
                assert (t.exit <= t.sl) if t.side == "buy" else (t.exit >= t.sl)
                assert t.net <= -(2.0 * 10) - 0.7 + 0.05
        return b

    asyncio.run(run())


def test_long_running_memory_is_bounded():
    """Hours of ticks: buffers stay capped (no unbounded growth)."""
    hub = MarketHub(DemoMarketSource(seed=1, realtime=False), "XAUUSD", "demo", wall_ms=lambda: 0)
    hub.spec = DEMO_SPEC
    sub = hub.subscribe(queue_size=500)
    gen = DemoTickGenerator("XAUUSD", 4000.0, T0, seed=3)
    tracemalloc.start()
    for _ in range(50_000):
        hub.ingest(gen.next_tick())
    first, _ = tracemalloc.get_traced_memory()
    for _ in range(100_000):
        hub.ingest(gen.next_tick())
    second, _ = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    assert all(len(hub.stats.history[tf]) <= HISTORY_LEN for tf in Timeframe)
    assert len(hub.stats.spreads) == SPREAD_WINDOW
    assert sub.queue.qsize() <= 500 and sub.dropped > 0
    assert second - first < 5_000_000  # < 5 MB growth over 100k more ticks


def test_performance_budgets():
    """Generous limits so CI catches regressions, not noise."""
    hub = MarketHub(DemoMarketSource(seed=1, realtime=False), "XAUUSD", "demo")
    src = DemoMarketSource(seed=2, realtime=False)
    hub.spec = DEMO_SPEC
    for tf in Timeframe:
        hub.seed_history(tf, asyncio.run(src.history("XAUUSD", tf, 500)))
    svc = AnalysisService(hub)
    t = time.perf_counter()
    for _ in range(10):
        svc.compute()
    per_analysis = (time.perf_counter() - t) / 10
    assert per_analysis < 0.25, per_analysis  # runs at most once per second

    gen = DemoTickGenerator("XAUUSD", 4000.0, T0, seed=4)
    ticks = [gen.next_tick() for _ in range(20_000)]
    t = time.perf_counter()
    for tk in ticks:
        hub.ingest(tk)
    rate = len(ticks) / (time.perf_counter() - t)
    assert rate > 5_000, rate  # gold rarely exceeds ~20 ticks/s live; replay at 60x needs ~1k/s


def test_replay_throughput_at_max_speed():
    async def run():
        s = ReplaySession(DemoMarketSource(), DEMO_SPEC, T0, lambda m: None)
        await s.load()
        t = time.perf_counter()
        await s.advance_to(T0 + 3_600_000)  # one hour of ticks
        return time.perf_counter() - t

    assert asyncio.run(run()) < 5.0  # 1 h of market in < 5 s => >720x real time
