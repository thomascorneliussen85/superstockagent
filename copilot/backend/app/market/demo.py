"""Synthetic XAUUSD feed for development and demonstrations.

This is NOT market data. It produces a plausible-looking random walk with
volatility regimes and a variable bid/ask spread so the UI, candle
aggregation and freshness monitoring can be exercised without MT5. Every
message derived from it is flagged ``synthetic`` and the UI labels it.
"""

from __future__ import annotations

import asyncio
import math
import random
import time
from collections.abc import AsyncIterator, Callable

from .candles import aggregate, bucket_start
from .models import Candle, SymbolSpec, Tick, Timeframe

DEMO_SPEC = SymbolSpec(
    symbol="XAUUSD",
    digits=2,
    point=0.01,
    contract_size=100.0,  # typical, but broker-specific in reality
    volume_min=0.01,
    volume_step=0.01,
    volume_max=100.0,
    currency_profit="USD",
    description="Gold vs US Dollar (SYNTHETIC DEMO FEED)",
    source="demo",
    tick_value=1.0,  # 0.01 USD move x 100 oz
    tick_size=0.01,
    broker_symbol="XAUUSD",
    currency_account="USD",
)


def generate_demo_history(
    symbol: str, end_ms: int, minutes: int, end_price: float, seed: int | None
) -> list[Candle]:
    """Synthetic 1-minute bars ending with the (open) bar containing ``end_ms``.

    The walk is generated backwards from ``end_price`` so live ticks continue
    seamlessly from the last close.
    """
    rng = random.Random(None if seed is None else seed + 1)
    last_start = bucket_start(end_ms, Timeframe.M1)
    closes = [end_price]
    vol = 0.9
    drift = 0.0
    paths: list[list[float]] = []
    for _ in range(minutes):
        vol = min(4.0, max(0.25, vol * math.exp(rng.gauss(0, 0.08))))
        drift = 0.98 * drift + rng.gauss(0, 0.03)
        # build a path backwards from the close of this minute to its open
        p = closes[-1]
        path = [p]
        for _ in range(6):
            p -= drift / 6 + rng.gauss(0, vol / 2.45)
            path.append(p)
        paths.append(path)
        closes.append(p)
    bars: list[Candle] = []
    for i, path in enumerate(reversed(paths)):
        start = last_start - (minutes - 1 - i) * Timeframe.M1.ms
        o, c = round(path[-1], 2), round(path[0], 2)
        bars.append(
            Candle(
                symbol=symbol,
                timeframe=Timeframe.M1,
                open_time_ms=start,
                open=o,
                high=round(max(path), 2),
                low=round(min(path), 2),
                close=c,
                tick_count=rng.randint(60, 220),
                max_spread=round(0.15 + abs(rng.gauss(0, 0.08)), 2),
                closed=i < minutes - 1,
            )
        )
    return bars


class DemoTickGenerator:
    """Pure, seedable tick generator (no I/O) - easy to test."""

    def __init__(
        self, symbol: str, start_price: float, start_ms: int, seed: int | None = None
    ) -> None:
        self.symbol = symbol
        self.rng = random.Random(seed)
        self.mid = start_price
        self.time_ms = start_ms
        self.vol = 0.08  # USD per tick, std-dev
        self.drift = 0.0

    def next_tick(self) -> Tick:
        r = self.rng
        self.time_ms += int(r.uniform(80, 700))
        # Slowly varying volatility regime and drift.
        self.vol = min(0.6, max(0.03, self.vol * math.exp(r.gauss(0, 0.05))))
        self.drift = 0.995 * self.drift + r.gauss(0, 0.002)
        if r.random() < 0.002:  # occasional burst (news-like)
            self.vol *= 3
        self.mid += self.drift + r.gauss(0, self.vol)
        self.mid = max(1.0, self.mid)
        spread = 0.12 + abs(r.gauss(0, 0.05)) + self.vol * 0.4
        if r.random() < 0.01:
            spread *= 3  # occasional spread widening
        bid = round(self.mid - spread / 2, 2)
        ask = round(bid + max(0.01, round(spread, 2)), 2)
        return Tick(symbol=self.symbol, time_ms=self.time_ms, bid=bid, ask=ask, volume=1.0)


class DemoMarketSource:
    name = "synthetic"
    is_synthetic = True

    def __init__(
        self,
        start_price: float = 4000.0,
        seed: int | None = None,
        clock_ms: Callable[[], int] | None = None,
        realtime: bool = True,
        pace_seconds: float = 0.0,
    ) -> None:
        self._pace = pace_seconds  # only used when realtime=False
        self._start_price = start_price
        self._seed = seed
        self._clock_ms = clock_ms or (lambda: int(time.time() * 1000))
        self._realtime = realtime
        self._closed = False
        self._history_1m: list[Candle] | None = None
        self._history_minutes = 0

    def _ensure_history(self, minutes: int) -> list[Candle]:
        if self._history_1m is None or self._history_minutes < minutes:
            self._history_1m = generate_demo_history(
                DEMO_SPEC.symbol, self._clock_ms(), minutes, self._start_price, self._seed
            )
            self._history_minutes = minutes
        return self._history_1m

    async def history(self, symbol: str, tf: Timeframe, count: int) -> list[Candle]:
        """Synthetic bars so indicators (e.g. EMA 200 on 1h) work immediately."""
        await self.symbol_spec(symbol)
        minutes = min(count * tf.ms // Timeframe.M1.ms, 60 * 24 * 30)
        bars = self._ensure_history(max(minutes, 1))
        return aggregate(bars, tf)[-count:]

    async def symbol_spec(self, symbol: str) -> SymbolSpec:
        if symbol != DEMO_SPEC.symbol:
            raise KeyError(f"demo source only provides {DEMO_SPEC.symbol}")
        return DEMO_SPEC

    async def ticks(self, symbol: str) -> AsyncIterator[Tick]:
        spec = await self.symbol_spec(symbol)
        self._closed = False
        start_price = self._history_1m[-1].close if self._history_1m else self._start_price
        gen = DemoTickGenerator(spec.symbol, start_price, self._clock_ms(), self._seed)
        while not self._closed:
            tick = gen.next_tick()
            if self._realtime:
                delay = (tick.time_ms - self._clock_ms()) / 1000
                if delay > 0:
                    await asyncio.sleep(delay)
                # Re-stamp with wall clock so freshness checks reflect reality.
                tick = Tick(tick.symbol, self._clock_ms(), tick.bid, tick.ask, tick.volume)
                gen.time_ms = tick.time_ms
            else:
                await asyncio.sleep(self._pace)
            yield tick

    async def close(self) -> None:
        self._closed = True
