"""Runs the analysis engine when market data changes and publishes results.

* Throttled: at most once per ``interval`` seconds, and only if new data
  arrived. This is cheap deterministic code, not an LLM call.
* Events (breakouts, structure breaks, ...) are only raised once per closed
  candle and kept in a short rolling log.
"""

from __future__ import annotations

import asyncio
import logging
import time
from collections import deque
from typing import Any

from ..hub import TIMEFRAMES, MarketHub
from .engine import analyze

log = logging.getLogger(__name__)
EVENT_LOG = 30


class AnalysisService:
    def __init__(self, hub: MarketHub, interval: float = 1.0) -> None:
        self.hub = hub
        self.interval = interval
        self._seen_version = -1
        self._seen_closed: dict[str, int | None] = {}
        self.events: deque[dict[str, Any]] = deque(maxlen=EVENT_LOG)
        self.last: dict[str, Any] | None = None
        self._task: asyncio.Task | None = None

    def compute(self) -> dict[str, Any] | None:
        hub = self.hub
        if hub.spec is None:
            return None
        result = analyze(
            {tf: hub.candles(tf) for tf in TIMEFRAMES},
            hub.spec,
            hub.stats.last_tick,
            hub.spread_samples(),
            int(time.time() * 1000),
        )
        for tf_key, tfa in result["timeframes"].items():
            closed_t = tfa.get("lastClosedT")
            if self._seen_closed.get(tf_key) == closed_t:
                continue
            first_run = tf_key not in self._seen_closed
            self._seen_closed[tf_key] = closed_t
            if not first_run:  # don't replay historical events at startup
                for e in tfa.get("events", []):
                    self.events.appendleft(e)
        result["recentEvents"] = list(self.events)
        self.last = result
        return result

    def tick(self) -> None:
        if self.hub.version == self._seen_version:
            return
        self._seen_version = self.hub.version
        try:
            result = self.compute()
        except Exception:  # noqa: BLE001 - analysis must never take the feed down
            log.exception("Analysis failed")
            return
        if result is not None:
            self.hub.publish({"type": "analysis", "data": result}, retain=True)

    async def run(self) -> None:
        while True:
            await asyncio.sleep(self.interval)
            self.tick()

    def start(self) -> None:
        self._task = asyncio.create_task(self.run(), name="analysis")

    async def stop(self) -> None:
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except (asyncio.CancelledError, Exception):
                pass
