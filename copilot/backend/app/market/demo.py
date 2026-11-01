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

from .models import SymbolSpec, Tick

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
)


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

    async def symbol_spec(self, symbol: str) -> SymbolSpec:
        if symbol != DEMO_SPEC.symbol:
            raise KeyError(f"demo source only provides {DEMO_SPEC.symbol}")
        return DEMO_SPEC

    async def ticks(self, symbol: str) -> AsyncIterator[Tick]:
        spec = await self.symbol_spec(symbol)
        gen = DemoTickGenerator(spec.symbol, self._start_price, self._clock_ms(), self._seed)
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
