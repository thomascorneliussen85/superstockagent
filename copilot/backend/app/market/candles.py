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

    def seed(self, candle: Candle) -> None:
        """Start from a historical (possibly still-forming) bar, e.g. from MT5.

        Later ticks in the same bucket extend it; ticks older than the bar's
        open time are ignored.
        """
        if candle.timeframe != self.timeframe:
            raise ValueError("timeframe mismatch")
        self._current = candle
        self._last_time_ms = candle.open_time_ms

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
            cur.closed = False  # a tick inside its period means it is still forming
            cur.high = max(cur.high, price)
            cur.low = min(cur.low, price)
            cur.close = price
            cur.tick_count += 1
            cur.max_spread = max(cur.max_spread, tick.spread)
        self._current = cur
        out.append(replace(cur))
        return out


def aggregate(candles: list[Candle], tf: Timeframe) -> list[Candle]:
    """Aggregate lower-timeframe candles (sorted, same symbol) into ``tf``.

    The result's last candle is marked open if any of its source candles is open.
    """
    out: list[Candle] = []
    for c in candles:
        start = bucket_start(c.open_time_ms, tf)
        if out and out[-1].open_time_ms == start:
            agg = out[-1]
            agg.high = max(agg.high, c.high)
            agg.low = min(agg.low, c.low)
            agg.close = c.close
            agg.tick_count += c.tick_count
            agg.max_spread = max(agg.max_spread, c.max_spread)
            agg.closed = agg.closed and c.closed
        else:
            out.append(replace(c, timeframe=tf, open_time_ms=start))
    if out:
        # Every bucket except the newest is complete by construction.
        for c in out[:-1]:
            c.closed = True
    return out
