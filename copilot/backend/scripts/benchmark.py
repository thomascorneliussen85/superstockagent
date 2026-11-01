"""Performance benchmark (run: python scripts/benchmark.py). Prints a table."""

from __future__ import annotations

import asyncio
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.analysis.service import AnalysisService  # noqa: E402
from app.coach.insights import find_insights  # noqa: E402
from app.coach.validation import evaluate_candidates  # noqa: E402
from app.hub import MarketHub  # noqa: E402
from app.market.demo import DEMO_SPEC, DemoMarketSource, DemoTickGenerator  # noqa: E402
from app.market.models import Timeframe  # noqa: E402
from app.replay.engine import ReplaySession  # noqa: E402

T0 = 1_780_000_000_000 - (1_780_000_000_000 % 60_000)


def timed(fn, n=1):
    t = time.perf_counter()
    for _ in range(n):
        fn()
    return (time.perf_counter() - t) / n


def main() -> None:
    hub = MarketHub(DemoMarketSource(seed=1, realtime=False), "XAUUSD", "demo")
    hub.spec = DEMO_SPEC
    src = DemoMarketSource(seed=2, realtime=False)
    for tf in Timeframe:
        hub.seed_history(tf, asyncio.run(src.history("XAUUSD", tf, 500)))
    svc = AnalysisService(hub)
    gen = DemoTickGenerator("XAUUSD", 4000.0, T0, seed=4)
    ticks = [gen.next_tick() for _ in range(50_000)]
    t_ingest = timed(lambda: [hub.ingest(t) for t in ticks])

    async def replay_hour():
        s = ReplaySession(DemoMarketSource(), DEMO_SPEC, T0, lambda m: None)
        await s.load()
        t = time.perf_counter()
        await s.advance_to(T0 + 3_600_000)
        return time.perf_counter() - t

    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tests"))
    from test_coach import make_trades  # noqa: E402

    trades = make_trades(n=1000)
    rows = [
        ("Analyse (4 TF x 500 lys)", f"{timed(svc.compute, 20) * 1000:.1f} ms"),
        ("Tick-inntak", f"{len(ticks) / t_ingest:,.0f} ticks/s"),
        ("Replay 1 time marked", f"{asyncio.run(replay_hour()):.2f} s"),
        ("Coach-mønstre (1000 handler)", f"{timed(lambda: find_insights(trades)):.2f} s"),
        ("Walk-forward (1000 handler)", f"{timed(lambda: evaluate_candidates(trades)):.2f} s"),
    ]
    w = max(len(r[0]) for r in rows)
    for name, val in rows:
        print(f"{name:<{w}}  {val}")


if __name__ == "__main__":
    main()
