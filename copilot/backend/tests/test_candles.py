from app.market.candles import CandleBuilder, bucket_start
from app.market.models import Tick, Timeframe

T0 = 1_700_000_040_000  # a minute boundary
assert T0 % 60_000 == 0


def tick(ms, bid, spread=0.2):
    return Tick("XAUUSD", ms, bid, round(bid + spread, 2))


def test_bucket_start():
    assert bucket_start(T0 + 59_999, Timeframe.M1) == T0
    assert bucket_start(T0 + 60_000, Timeframe.M1) == T0 + 60_000


def test_ohlc_within_bucket():
    b = CandleBuilder("XAUUSD", Timeframe.M1)
    b.update(tick(T0 + 1000, 10.0))
    b.update(tick(T0 + 2000, 12.0, spread=0.5))
    out = b.update(tick(T0 + 3000, 9.0))
    c = out[-1]
    assert (c.open, c.high, c.low, c.close, c.tick_count) == (10.0, 12.0, 9.0, 9.0, 3)
    assert abs(c.max_spread - 0.5) < 1e-9
    assert not c.closed


def test_boundary_closes_previous_and_opens_new():
    b = CandleBuilder("XAUUSD", Timeframe.M1)
    b.update(tick(T0 + 1000, 10.0))
    out = b.update(tick(T0 + 60_000, 11.0))
    assert len(out) == 2
    assert out[0].closed and out[0].open_time_ms == T0 and out[0].close == 10.0
    assert not out[1].closed and out[1].open_time_ms == T0 + 60_000 and out[1].open == 11.0


def test_published_candles_are_snapshots():
    b = CandleBuilder("XAUUSD", Timeframe.M1)
    first = b.update(tick(T0, 10.0))[0]
    b.update(tick(T0 + 1, 20.0))
    assert first.high == 10.0  # earlier snapshot not mutated -> no future leakage


def test_out_of_order_tick_ignored():
    b = CandleBuilder("XAUUSD", Timeframe.M1)
    b.update(tick(T0 + 5000, 10.0))
    assert b.update(tick(T0 + 4000, 50.0)) == []
    assert b.current.high == 10.0


def test_gap_skips_empty_buckets():
    b = CandleBuilder("XAUUSD", Timeframe.M5)
    b.update(tick(T0, 10.0))
    out = b.update(tick(T0 + 3_600_000, 11.0))
    assert out[0].closed and out[1].open_time_ms == bucket_start(T0 + 3_600_000, Timeframe.M5)
