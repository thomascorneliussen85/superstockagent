"""Market hub: consumes one data source and fans out to WebSocket clients.

Design notes
------------
* One producer task per symbol; any number of subscribers.
* Each subscriber has a bounded queue. If a slow client falls behind, the
  oldest messages are dropped (ticks are conflatable; the next tick or
  candle supersedes them) - a slow UI never blocks the feed.
* On (re)connect the hub seeds its candle history from the source (MT5 bars)
  so indicators such as EMA 200 are available immediately.
* Freshness is tracked from the last tick's arrival time, and a ``status``
  message is pushed whenever it changes (live <-> stale <-> disconnected).
* The producer task restarts the source with exponential backoff on errors
  (automatic reconnection).
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import time
from collections import deque
from collections.abc import Callable
from dataclasses import dataclass, field, replace
from typing import Any

from .market.candles import CandleBuilder
from .market.models import Candle, SymbolSpec, Tick, Timeframe
from .market.source import MarketDataSource

log = logging.getLogger(__name__)

TIMEFRAMES = (Timeframe.M1, Timeframe.M5, Timeframe.M15, Timeframe.H1)
HISTORY_LEN = 500  # closed candles kept per timeframe (EMA 200 needs >= 200)
SNAPSHOT_CANDLES = 120  # candles per timeframe sent to a newly connected client
SPREAD_WINDOW = 3000  # recent ticks used for spread statistics
OLD_TICK_MS = 10_000  # ticks older than this on arrival are treated as stale


class FeedState:
    STARTING = "starting"
    LIVE = "live"
    STALE = "stale"
    DISCONNECTED = "disconnected"


@dataclass(eq=False)
class Subscriber:
    queue: asyncio.Queue[dict[str, Any]]
    dropped: int = 0

    def offer(self, msg: dict[str, Any]) -> None:
        while True:
            try:
                self.queue.put_nowait(msg)
                return
            except asyncio.QueueFull:
                with contextlib.suppress(asyncio.QueueEmpty):
                    self.queue.get_nowait()
                    self.dropped += 1


@dataclass
class HubStats:
    ticks_received: int = 0
    last_tick_wall_ms: int | None = None
    last_tick: Tick | None = None
    state: str = FeedState.STARTING
    reconnects: int = 0
    last_error: str | None = None
    history: dict[Timeframe, deque[Candle]] = field(
        default_factory=lambda: {tf: deque(maxlen=HISTORY_LEN) for tf in TIMEFRAMES}
    )
    spreads: deque[float] = field(default_factory=lambda: deque(maxlen=SPREAD_WINDOW))


class MarketHub:
    def __init__(
        self,
        source: MarketDataSource,
        symbol: str,
        mode: str,
        stale_after_seconds: float = 5.0,
        wall_ms: Callable[[], int] | None = None,
        initial_backoff_seconds: float = 1.0,
    ) -> None:
        self._initial_backoff = initial_backoff_seconds
        self.source = source
        self.symbol = symbol
        self.configured_mode = mode
        self.stale_after_ms = int(stale_after_seconds * 1000)
        self._wall_ms = wall_ms or (lambda: int(time.time() * 1000))
        self.spec: SymbolSpec | None = None
        self.stats = HubStats()
        self._builders = {tf: CandleBuilder(symbol, tf) for tf in TIMEFRAMES}
        self._subs: set[Subscriber] = set()
        self._tasks: list[asyncio.Task] = []
        self._retained: dict[str, dict[str, Any]] = {}
        #: Increments on every change of market data; consumers poll it.
        self.version = 0
        #: Increments whenever any timeframe closes a candle.
        self.closed_version = 0

    # ---- derived info ----------------------------------------------------
    @property
    def mode(self) -> str:
        """Actual mode. For MT5 this reflects the real account type (demo/live)."""
        return getattr(self.source, "resolved_mode", None) or self.configured_mode

    # ---- lifecycle -------------------------------------------------------
    async def start(self) -> None:
        self._tasks.append(asyncio.create_task(self._run_feed(), name="hub-feed"))
        self._tasks.append(asyncio.create_task(self._watch_freshness(), name="hub-fresh"))

    async def stop(self) -> None:
        for t in self._tasks:
            t.cancel()
        for t in self._tasks:
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await t
        self._tasks.clear()
        await self.source.close()

    # ---- subscriptions ---------------------------------------------------
    def subscribe(self, queue_size: int = 500) -> Subscriber:
        sub = Subscriber(asyncio.Queue(maxsize=queue_size))
        self._subs.add(sub)
        return sub

    def unsubscribe(self, sub: Subscriber) -> None:
        self._subs.discard(sub)

    @property
    def subscriber_count(self) -> int:
        return len(self._subs)

    def _broadcast(self, msg: dict[str, Any]) -> None:
        for sub in list(self._subs):
            sub.offer(msg)

    def publish(self, msg: dict[str, Any], retain: bool = False) -> None:
        """Send a message to all clients; retained messages are replayed to new clients."""
        if retain:
            self._retained[msg["type"]] = msg
        self._broadcast(msg)

    # ---- read access for analysis ------------------------------------------
    def candles(self, tf: Timeframe, include_forming: bool = True) -> list[Candle]:
        out = list(self.stats.history[tf])
        cur = self._builders[tf].current
        if include_forming and cur is not None:
            out.append(replace(cur))
        return out

    def spread_samples(self) -> list[float]:
        return list(self.stats.spreads)

    # ---- snapshot for new clients ----------------------------------------
    def status_payload(self) -> dict[str, Any]:
        now = self._wall_ms()
        last = self.stats.last_tick_wall_ms
        return {
            "state": self.stats.state,
            "mode": self.mode,
            "source": self.source.name,
            "synthetic": self.source.is_synthetic,
            "symbol": self.symbol,
            "lastTickAgeMs": None if last is None else max(0, now - last),
            "ticksReceived": self.stats.ticks_received,
            "reconnects": self.stats.reconnects,
            "lastError": self.stats.last_error,
            "account": getattr(self.source, "account", None),
            "warnings": list(getattr(self.source, "warnings", []) or []),
            "serverTime": now,
        }

    def snapshot(self) -> list[dict[str, Any]]:
        digits = self.spec.digits if self.spec else 2
        msgs: list[dict[str, Any]] = [{"type": "status", "data": self.status_payload()}]
        if self.spec:
            msgs.append({"type": "symbol", "data": self.spec.to_wire()})
        for tf in TIMEFRAMES:
            candles = [c.to_wire(digits) for c in self.candles(tf)[-SNAPSHOT_CANDLES:]]
            msgs.append({"type": "candles", "data": {"tf": tf.value, "candles": candles}})
        if self.stats.last_tick:
            msgs.append({"type": "tick", "data": self.stats.last_tick.to_wire(digits)})
        msgs.extend(self._retained.values())
        return msgs

    # ---- internals -------------------------------------------------------
    def _set_state(self, state: str) -> None:
        if state != self.stats.state:
            self.stats.state = state
            self._broadcast({"type": "status", "data": self.status_payload()})

    def seed_history(self, tf: Timeframe, candles: list[Candle]) -> None:
        """Load historical bars. The last bar may be the still-forming one."""
        if not candles:
            return
        candles = sorted(candles, key=lambda c: c.open_time_ms)
        hist = self.stats.history[tf]
        hist.clear()
        last = candles[-1]
        for c in candles[:-1]:
            hist.append(replace(c, closed=True))
        if last.closed:
            hist.append(replace(last))
        else:
            self._builders[tf].seed(replace(last))
        self.version += 1
        self.closed_version += 1

    def reset_history(self) -> None:
        for tf in TIMEFRAMES:
            self.stats.history[tf].clear()
            self._builders[tf] = CandleBuilder(self.symbol, tf)

    def ingest(self, tick: Tick) -> None:
        """Process one tick (public for tests and replay)."""
        digits = self.spec.digits if self.spec else 2
        self.stats.ticks_received += 1
        self.stats.last_tick = tick
        now = self._wall_ms()
        # A tick much older than "now" (e.g. last price before the weekend) must not
        # look fresh. Small clock differences (< 10 s) are ignored.
        old = now - tick.time_ms > OLD_TICK_MS
        self.stats.last_tick_wall_ms = tick.time_ms if old else now
        self.stats.spreads.append(tick.spread)
        self._set_state(FeedState.STALE if old else FeedState.LIVE)
        self._broadcast({"type": "tick", "data": tick.to_wire(digits)})
        for tf, builder in self._builders.items():
            for candle in builder.update(tick):
                if candle.closed:
                    self.stats.history[tf].append(candle)
                    self.closed_version += 1
                self._broadcast({"type": "candle", "data": candle.to_wire(digits)})
        self.version += 1

    async def _load_history(self) -> None:
        history = getattr(self.source, "history", None)
        if history is None:
            return
        self.reset_history()
        for tf in TIMEFRAMES:
            try:
                bars = await history(self.symbol, tf, HISTORY_LEN)
            except Exception:  # noqa: BLE001 - history is best effort
                log.exception("Could not load %s history", tf.value)
                continue
            self.seed_history(tf, bars)
        digits = self.spec.digits if self.spec else 2
        for tf in TIMEFRAMES:
            candles = [c.to_wire(digits) for c in self.candles(tf)[-SNAPSHOT_CANDLES:]]
            self._broadcast({"type": "candles", "data": {"tf": tf.value, "candles": candles}})

    async def _run_feed(self) -> None:
        backoff = self._initial_backoff
        while True:
            try:
                self.spec = await self.source.symbol_spec(self.symbol)
                self._broadcast({"type": "symbol", "data": self.spec.to_wire()})
                await self._load_history()
                self._broadcast({"type": "status", "data": self.status_payload()})
                async for tick in self.source.ticks(self.symbol):
                    if self.stats.last_error:
                        self.stats.last_error = None
                    self.ingest(tick)
                    backoff = self._initial_backoff
                log.warning("Market source ended; restarting")
            except asyncio.CancelledError:
                raise
            except Exception as exc:  # noqa: BLE001 - feed must survive any source error
                log.exception("Market source failed")
                self.stats.last_error = (
                    str(exc) if getattr(exc, "user_facing", False) else f"{type(exc).__name__}: {exc}"
                )
            self.stats.reconnects += 1
            self.stats.state = FeedState.STARTING  # force a status push below
            self._set_state(FeedState.DISCONNECTED)
            with contextlib.suppress(Exception):
                await self.source.close()
            await asyncio.sleep(backoff)
            backoff = min(backoff * 2, 30.0)

    def check_freshness(self) -> None:
        last = self.stats.last_tick_wall_ms
        if last is None or self.stats.state == FeedState.DISCONNECTED:
            return
        age = self._wall_ms() - last
        self._set_state(FeedState.STALE if age > self.stale_after_ms else FeedState.LIVE)

    async def _watch_freshness(self) -> None:
        while True:
            await asyncio.sleep(1.0)
            self.check_freshness()
