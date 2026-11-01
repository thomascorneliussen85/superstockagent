"""Tick-by-tick historical replay with a virtual clock.

Look-ahead protection is structural:
* Future ticks are held privately in ``_pending`` and are only *released* to
  the replay market state when the virtual clock passes them.
* History before the start comes only from bars that had closed before it.
* Analysis, AI questions and simulated fills only ever see the released state.
A unit test checks that no candle, tick or analysis value is later than the
virtual clock.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import time
from collections import deque
from collections.abc import Callable
from typing import Any

from ..analysis.service import AnalysisService
from ..hub import TIMEFRAMES, MarketHub
from ..market.candles import aggregate
from ..market.demo import DEMO_SPEC, DemoTickGenerator, generate_demo_history
from ..market.models import Candle, SymbolSpec, Tick, Timeframe
from .broker import SimBroker

log = logging.getLogger(__name__)
CHUNK_MS = 30 * 60_000
SPEEDS = (1, 2, 5, 10, 30, 60)
GAP_SKIP_MS = 10 * 60_000


class _NullSource:
    name = "replay"
    is_synthetic = False

    async def close(self) -> None:  # pragma: no cover - never started
        return None


def ticks_from_bars(bars: list[Candle], symbol: str) -> list[Tick]:
    """Fallback when the broker has no tick history: a simple O->H/L->C path inside
    each 1-minute bar (clearly labelled as synthetic intrabar movement)."""
    out: list[Tick] = []
    for b in bars:
        spread = max(b.max_spread, 0.01)
        up_first = b.close >= b.open
        path = [b.open, b.low, b.high, b.close] if up_first else [b.open, b.high, b.low, b.close]
        for i, p in enumerate(path):
            out.append(Tick(symbol, b.open_time_ms + i * 15_000, round(p, 2), round(p + spread, 2)))
    return out


class ReplaySession:
    def __init__(
        self,
        source: Any,
        spec: SymbolSpec,
        start_ms: int,
        emit: Callable[[dict[str, Any]], None],
        speed: float = 1.0,
        broker: SimBroker | None = None,
        wall: Callable[[], float] = time.monotonic,
    ) -> None:
        self.source = source
        self.spec = spec
        self.start_ms = start_ms
        self.clock_ms = start_ms
        self.speed = speed
        self.paused = True
        self.emit = emit
        self._wall = wall
        self._last_wall: float | None = None
        self.broker = broker or SimBroker(contract_size=spec.contract_size)
        self.data_quality = "ticks"
        self._pending: deque[Tick] = deque()
        self._loaded_until = start_ms
        self._synthetic_gen: DemoTickGenerator | None = None
        self.ended = False
        self.events: list[dict[str, Any]] = []
        # Released market state, built only from data <= clock
        self.hub = MarketHub(
            _NullSource(), spec.symbol, "replay", stale_after_seconds=1e9, wall_ms=lambda: self.clock_ms
        )
        self.hub.spec = spec
        self._buffer: dict[str, dict[str, Any]] = {}
        self.hub._broadcast = self._capture  # type: ignore[method-assign]
        self.analysis = AnalysisService(self.hub)

    # ---- data loading ---------------------------------------------------------------
    async def load(self) -> None:
        src = self.source
        if hasattr(src, "rates_before") and hasattr(src, "ticks_range"):
            for tf in TIMEFRAMES:
                bars = await src.rates_before(self.spec.symbol, tf, self.start_ms, 300)
                self.hub.stats.history[tf].extend(b for b in bars if b.open_time_ms + tf.ms <= self.start_ms)
        else:
            # Demo mode: synthetic history and ticks, deterministic for a given start time.
            hist = generate_demo_history(self.spec.symbol, self.start_ms - 1, 300 * 60, 4000.0, self.start_ms)
            closed = [c for c in hist if c.open_time_ms + 60_000 <= self.start_ms]
            for tf in TIMEFRAMES:
                agg = [c for c in aggregate(closed, tf) if c.open_time_ms + tf.ms <= self.start_ms]
                for c in agg:
                    c.closed = True
                self.hub.stats.history[tf].extend(agg[-300:])
            start_price = closed[-1].close if closed else 4000.0
            self._synthetic_gen = DemoTickGenerator(
                self.spec.symbol, start_price, self.start_ms, self.start_ms
            )
            self.data_quality = "synthetic"
        await self._ensure_loaded(self.start_ms + CHUNK_MS)
        self.analysis.compute()
        self._emit_snapshot()

    async def _ensure_loaded(self, until_ms: int, stop_on_data: bool = False) -> None:
        while self._loaded_until < until_ms and not (stop_on_data and self._pending):
            a, b = self._loaded_until, self._loaded_until + CHUNK_MS
            ticks: list[Tick] = []
            if self._synthetic_gen is not None:
                g = self._synthetic_gen
                while g.time_ms < b:
                    ticks.append(g.next_tick())
            else:
                with contextlib.suppress(Exception):
                    ticks = await self.source.ticks_range(self.spec.symbol, a, b)
                if not ticks and hasattr(self.source, "rates_range"):
                    with contextlib.suppress(Exception):
                        bars = await self.source.rates_range(self.spec.symbol, Timeframe.M1, a, b)
                        ticks = ticks_from_bars(bars, self.spec.symbol)
                        if ticks:
                            self.data_quality = "bars"
            ticks = [t for t in ticks if a <= t.time_ms < b]
            ticks.sort(key=lambda t: t.time_ms)
            self._pending.extend(ticks)
            self._loaded_until = b

    # ---- release ------------------------------------------------------------------------
    def _capture(self, msg: dict[str, Any]) -> None:
        t = msg["type"]
        # Keep the final state of a candle that just closed as well as the new one.
        if t == "candle":
            key = f"candle:{msg['data']['tf']}:{msg['data']['t']}"
        elif t == "candles":
            key = f"candles:{msg['data']['tf']}"
        else:
            key = t
        self._buffer[key] = msg

    def _flush(self) -> None:
        for m in self._buffer.values():
            self.emit({"type": "replay", "data": m})
        self._buffer.clear()

    async def advance_to(self, target_ms: int) -> None:
        await self._ensure_loaded(target_ms + CHUNK_MS)
        while self._pending and self._pending[0].time_ms <= target_ms:
            tick = self._pending.popleft()
            self.clock_ms = tick.time_ms
            self.hub.ingest(tick)
            for tr in self.broker.on_tick(tick):
                self.events.append({"type": "closed", "trade": tr.to_wire()})
        self.clock_ms = max(self.clock_ms, target_ms)
        if not self._pending and self._synthetic_gen is None:
            # Look further ahead (weekends, holidays); end if there is nothing for 3 days.
            await self._ensure_loaded(self._loaded_until + 3 * 86_400_000, stop_on_data=True)
            if not self._pending:
                self.ended = True
                self.paused = True
        if self._pending and self._pending[0].time_ms - self.clock_ms > GAP_SKIP_MS:
            # Market closed (e.g. weekend): skip the dead time instead of waiting for it.
            self.events.append({"type": "gap", "fromMs": self.clock_ms, "toMs": self._pending[0].time_ms})
            self.clock_ms = self._pending[0].time_ms - 1000

    async def step(self) -> None:
        now = self._wall()
        if self.paused or self.ended:
            self._last_wall = now
            return
        elapsed = 0.0 if self._last_wall is None else now - self._last_wall
        self._last_wall = now
        await self.advance_to(self.clock_ms + int(elapsed * 1000 * self.speed))

    # ---- controls -------------------------------------------------------------------------
    def set_paused(self, paused: bool) -> None:
        self.paused = paused
        self._last_wall = self._wall()

    def set_speed(self, speed: float) -> None:
        self.speed = max(0.25, min(240.0, float(speed)))

    async def jump(self, ms: int) -> None:
        await self.advance_to(self.clock_ms + max(0, int(ms)))

    # ---- state ------------------------------------------------------------------------------
    def state(self) -> dict[str, Any]:
        return {
            "active": True,
            "startMs": self.start_ms,
            "clockMs": self.clock_ms,
            "speed": self.speed,
            "paused": self.paused,
            "ended": self.ended,
            "dataQuality": self.data_quality,
            "account": self.broker.state(),
            "events": self.events[-10:],
        }

    def _emit_snapshot(self) -> None:
        for m in self.hub.snapshot():
            self.emit({"type": "replay", "data": m})
        if self.analysis.last:
            self.emit({"type": "replay", "data": {"type": "analysis", "data": self.analysis.last}})


class ReplayManager:
    """One replay session at a time, driven by WebSocket commands."""

    def __init__(self, hub: MarketHub, ai: Any = None, tick_s: float = 0.05) -> None:
        self.hub = hub
        self.ai = ai
        self.tick_s = tick_s
        self.session: ReplaySession | None = None
        self._task: asyncio.Task | None = None
        self._last_analysis = 0.0
        self._last_state = 0.0
        self.error: str | None = None

    def _emit(self, msg: dict[str, Any]) -> None:
        self.hub.publish(msg)

    def publish_state(self) -> None:
        st = self.session.state() if self.session else {"active": False}
        if self.error:
            st["error"] = self.error
        self.hub.publish({"type": "replay_state", "data": st})

    async def start(
        self, start_ms: int, speed: float = 1.0, balance: float = 10_000.0, commission_per_lot: float = 7.0
    ) -> None:
        await self.stop()
        self.error = None
        spec = self.hub.spec or DEMO_SPEC
        if start_ms > time.time() * 1000 - 60_000:
            self.error = "Starttidspunktet må ligge i fortiden."
            self.publish_state()
            return
        broker = SimBroker(
            contract_size=spec.contract_size, commission_per_lot=commission_per_lot, balance=balance
        )
        s = ReplaySession(self.hub.source, spec, start_ms, self._emit, speed, broker)
        try:
            await s.load()
        except Exception as exc:  # noqa: BLE001
            self.error = f"Kunne ikke laste historikk: {exc}"
            self.publish_state()
            return
        self.session = s
        self._task = asyncio.create_task(self._run(), name="replay")
        self.publish_state()

    async def stop(self) -> None:
        if self._task:
            self._task.cancel()
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await self._task
        self._task = None
        self.session = None

    async def command(self, msg: dict[str, Any]) -> None:
        t = msg.get("type")
        s = self.session
        try:
            if t == "replay_start":
                await self.start(
                    int(msg["startMs"]),
                    float(msg.get("speed", 1)),
                    float(msg.get("balance", 10_000)),
                    float(msg.get("commissionPerLot", 7.0)),
                )
                return
            if s is None:
                return
            if t == "replay_control":
                a = msg.get("action")
                if a == "pause":
                    s.set_paused(True)
                elif a == "resume":
                    s.set_paused(False)
                elif a == "speed":
                    s.set_speed(float(msg.get("value", 1)))
                elif a == "jump":
                    await s.jump(int(msg.get("value", 60_000)))
                elif a == "stop":
                    await self.stop()
            elif t == "replay_order":
                s.broker.market_order(
                    msg["side"], float(msg["volume"]), msg.get("slDistance"), msg.get("tpDistance")
                )
            elif t == "replay_close":
                if msg.get("id") == "all":
                    s.broker.close_all()
                else:
                    s.broker.close(int(msg["id"]))
            elif t == "replay_ai" and self.ai is not None:
                res = await self.ai.comment_on_replay(s.hub, s.analysis)
                self.hub.publish(
                    {"type": "replay", "data": {"type": "ai", "data": res}}
                    if "summary" in res
                    else {"type": "replay_state", "data": {**s.state(), "error": res.get("error")}}
                )
                return
        except (ValueError, KeyError, TypeError) as exc:
            self.error = str(exc)
        self.publish_state()

    async def _run(self) -> None:
        while self.session is not None:
            s = self.session
            try:
                await s.step()
                s._flush()
                now = time.monotonic()
                if now - self._last_analysis > 1.0:
                    self._last_analysis = now
                    s.analysis.tick()
                    s._flush()
                if now - self._last_state > 0.25:
                    self._last_state = now
                    self.publish_state()
            except Exception:  # noqa: BLE001
                log.exception("Replay step failed")
            await asyncio.sleep(self.tick_s)
