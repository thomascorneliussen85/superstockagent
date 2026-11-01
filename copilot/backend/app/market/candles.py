"""Deterministic tick-to-candle aggregation.

The same builder is used for live data and (later) historical replay, so a
candle seen during replay is bit-for-bit what it would have been live, and a
candle is never emitted with information from after its last tick.
"""

from __future__ import annotations

from dataclasses import replace

from .models import Candle, Tick, Timeframe


def bucket_start(time_ms: int, tf: Timeframe) -> int:
    return time_ms - (time_ms % tf.ms)


class CandleBuilder:
    def __init__(self, symbol: str, timeframe: Timeframe) -> None:
        self.symbol = symbol
        self.timeframe = timeframe
        self._current: Candle | None = None
        self._last_time_ms: int | None = None

    @property
    def current(self) -> Candle | None:
        return self._current

    def update(self, tick: Tick) -> list[Candle]:
        """Apply one tick. Returns candles to publish, in order.

        At a bucket boundary the previous candle is returned with
        ``closed=True`` followed by the new open candle. Out-of-order ticks
        (older than the last accepted tick) are ignored.
        """
        if tick.symbol != self.symbol:
            raise ValueError(f"tick for {tick.symbol} sent to {self.symbol} builder")
        if self._last_time_ms is not None and tick.time_ms < self._last_time_ms:
            return []
        self._last_time_ms = tick.time_ms

        price = tick.bid
        start = bucket_start(tick.time_ms, self.timeframe)
        out: list[Candle] = []
        cur = self._current
        if cur is not None and start != cur.open_time_ms:
            cur.closed = True
            out.append(replace(cur))
            cur = None
        if cur is None:
            cur = Candle(
                symbol=self.symbol,
                timeframe=self.timeframe,
                open_time_ms=start,
                open=price,
                high=price,
                low=price,
                close=price,
                tick_count=1,
                max_spread=tick.spread,
            )
        else:
            cur.high = max(cur.high, price)
            cur.low = min(cur.low, price)
            cur.close = price
            cur.tick_count += 1
            cur.max_spread = max(cur.max_spread, tick.spread)
        self._current = cur
        out.append(replace(cur))
        return out
