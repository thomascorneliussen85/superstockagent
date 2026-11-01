import asyncio

from app.hub import FeedState, MarketHub
from app.market.demo import DemoMarketSource
from app.market.models import Tick


class FakeClock:
    def __init__(self):
        self.now = 1_700_000_040_000

    def __call__(self):
        return self.now


def make_hub(clock):
    return MarketHub(DemoMarketSource(seed=1, realtime=False), "XAUUSD", "demo", 5.0, wall_ms=clock)


def test_freshness_transitions():
    clock = FakeClock()
    hub = make_hub(clock)

    async def run():
        sub = hub.subscribe()
        hub.ingest(Tick("XAUUSD", clock.now, 10.0, 10.2))
        assert hub.stats.state == FeedState.LIVE
        clock.now += 6000
        hub.check_freshness()
        assert hub.stats.state == FeedState.STALE
        hub.ingest(Tick("XAUUSD", clock.now, 10.0, 10.2))
        assert hub.stats.state == FeedState.LIVE
        types = []
        while not sub.queue.empty():
            types.append(sub.queue.get_nowait()["type"])
        assert types.count("status") == 3

    asyncio.run(run())


def test_slow_subscriber_drops_oldest():
    clock = FakeClock()
    hub = make_hub(clock)

    async def run():
        sub = hub.subscribe(queue_size=10)
        for i in range(50):
            hub.ingest(Tick("XAUUSD", clock.now + i, 10.0 + i, 10.2 + i))
        assert sub.queue.qsize() == 10
        assert sub.dropped > 0
        last = None
        while not sub.queue.empty():
            last = sub.queue.get_nowait()
        assert last["data"]["c"] == 59.0  # newest data survives

    asyncio.run(run())


class FailingSource(DemoMarketSource):
    def __init__(self):
        super().__init__(seed=1, realtime=False)
        self.calls = 0

    async def ticks(self, symbol):
        self.calls += 1
        if self.calls == 1:
            raise ConnectionError("terminal offline")
        async for t in super().ticks(symbol):
            yield t


def test_reconnects_after_source_error():
    async def run():
        src = FailingSource()
        hub = MarketHub(src, "XAUUSD", "demo", initial_backoff_seconds=0.01)
        await hub.start()
        for _ in range(100):
            await asyncio.sleep(0.005)
            if hub.stats.ticks_received:
                break
        await hub.stop()
        assert hub.stats.reconnects >= 1
        assert "terminal offline" in (hub.stats.last_error or "")
        assert hub.stats.ticks_received > 0

    asyncio.run(run())
