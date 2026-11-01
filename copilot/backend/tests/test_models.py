from datetime import UTC, datetime

import pytest

from app.market.demo import DemoTickGenerator
from app.market.models import Tick, utc_ms


def test_ask_below_bid_rejected():
    with pytest.raises(ValueError):
        Tick("XAUUSD", 0, 10.0, 9.99)


def test_naive_datetime_rejected():
    with pytest.raises(ValueError):
        utc_ms(datetime(2026, 1, 1))
    assert utc_ms(datetime(1970, 1, 1, tzinfo=UTC)) == 0


def test_demo_generator_deterministic_and_sane():
    a = DemoTickGenerator("XAUUSD", 4000.0, 0, seed=7)
    b = DemoTickGenerator("XAUUSD", 4000.0, 0, seed=7)
    ta = [a.next_tick() for _ in range(2000)]
    tb = [b.next_tick() for _ in range(2000)]
    assert ta == tb
    times = [t.time_ms for t in ta]
    assert times == sorted(times)
    assert all(t.ask > t.bid for t in ta)
    assert all(0.01 <= t.spread < 10 for t in ta)
