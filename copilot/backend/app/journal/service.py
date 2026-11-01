"""Keeps the journal in sync with MT5 and enriches trades with context.

* Imports deals incrementally (insert-only, duplicates ignored), first run
  imports the full available history.
* Rebuilds round-trip trades deterministically from the raw deals.
* Adds entry context: live analysis when the position was seen live,
  otherwise reconstructed from bars closed before the entry.
* Notifies listeners (the coach) about newly closed trades.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import time
from collections.abc import Callable
from typing import Any

from ..hub import MarketHub
from ..market.models import Timeframe
from .build import build_trades
from .context import TFS, compact_context, context_from_bars
from .store import JournalStore

log = logging.getLogger(__name__)
FULL_HISTORY_FROM_MS = 1_420_070_400_000  # 2015-01-01
OVERLAP_MS = 86_400_000
CONTEXT_PER_SYNC = 25


class JournalService:
    def __init__(self, hub: MarketHub, store: JournalStore, interval: float = 60.0) -> None:
        self.hub = hub
        self.store = store
        self.interval = interval
        self.listeners: list[Callable[[dict[str, Any]], Any]] = []
        self.last_sync_ms: int | None = None
        self.last_error: str | None = None
        self._task: asyncio.Task | None = None
        self._kick = asyncio.Event()
        self._seen_live: set[int] = set()

    @property
    def available(self) -> bool:
        return hasattr(self.hub.source, "history_deals")

    def specs(self) -> dict[str, dict[str, Any]]:
        spec = self.hub.spec
        if not spec:
            return {}
        d = {
            "tickSize": spec.tick_size,
            "tickValue": spec.tick_value,
            "tickValueLoss": spec.tick_value_loss,
            "contractSize": spec.contract_size,
        }
        return {spec.symbol: d, (spec.broker_symbol or spec.symbol): d}

    # ---- live hooks (from the account monitor) ---------------------------------------
    def on_live_positions(self, positions: list[dict[str, Any]], analysis: dict[str, Any] | None) -> None:
        for p in positions:
            pid = p["ticket"]
            self.store.set_levels(pid, p.get("sl") or None, p.get("tp") or None, "live")
            if pid not in self._seen_live:
                self._seen_live.add(pid)
                if analysis and not self.store.has_context(pid):
                    direction = "long" if p["type"] == "buy" else "short"
                    ctx = compact_context(analysis, direction)
                    if self.hub.stats.last_tick:
                        ctx["spreadCost"] = round(
                            self.hub.stats.last_tick.spread
                            * (p.get("spec", {}).get("contractSize") or 0)
                            * p["volume"],
                            2,
                        )
                    self.store.set_context(pid, ctx, "live")

    # ---- sync ----------------------------------------------------------------------------
    async def sync(self) -> dict[str, Any]:
        src = self.hub.source
        if not self.available:
            return {"available": False}
        now = int(time.time() * 1000)
        last = self.store.last_deal_ms()
        start = FULL_HISTORY_FROM_MS if last is None else last - OVERLAP_MS
        deals = await src.history_deals(start, now)
        new = self.store.insert_deals(deals)

        # Initial SL/TP from the entry order, for positions we never saw live.
        known = self.store.levels()
        entry_positions = {d["positionId"] for d in deals if d["entry"] == 0 and d["positionId"]}
        for pid in sorted(entry_positions - set(known))[:200]:
            with contextlib.suppress(Exception):
                orders = await src.history_orders(pid)
                first = min(orders, key=lambda o: o["timeMs"]) if orders else None
                if first:
                    self.store.set_levels(pid, first["sl"] or None, first["tp"] or None, "order")

        before = {t["position_id"] for t in self.store.trades()}
        trades = build_trades(self.store.deals(), self.store.levels(), self.specs())
        self.store.replace_trades(trades)
        await self._fill_context(trades)

        newly_closed = [t for t in self.store.trades() if t["position_id"] not in before]
        if last is not None:  # don't flood listeners with the whole history on first import
            for t in newly_closed:
                for cb in self.listeners:
                    with contextlib.suppress(Exception):
                        res = cb(t)
                        if asyncio.iscoroutine(res):
                            await res
        self.last_sync_ms = now
        self.last_error = None
        return {"available": True, "newDeals": new, "trades": len(trades), "newlyClosed": len(newly_closed)}

    async def _fill_context(self, trades: list[dict[str, Any]]) -> None:
        src = self.hub.source
        spec = self.hub.spec
        if spec is None or not hasattr(src, "rates_before"):
            return
        names = {spec.symbol, spec.broker_symbol}
        todo = [
            t
            for t in reversed(trades)
            if t["symbol"] in names and not self.store.has_context(t["position_id"])
        ]
        for t in todo[:CONTEXT_PER_SYNC]:
            try:
                bars = {tf: await src.rates_before(spec.symbol, tf, t["open_ms"], 250) for tf in TFS}
            except Exception as exc:  # noqa: BLE001
                log.debug("context for %s failed: %s", t["position_id"], exc)
                continue
            ctx = context_from_bars(bars, spec, t["direction"], t["volume"])
            self.store.set_context(t["position_id"], ctx, "history")

    def request_sync(self) -> None:
        self._kick.set()

    async def run(self) -> None:
        await asyncio.sleep(5)  # let the market source connect first
        while True:
            try:
                if self.hub.spec is not None:
                    await self.sync()
            except Exception as exc:  # noqa: BLE001
                self.last_error = str(exc)
                log.warning("Journal sync failed: %s", exc)
            self._kick.clear()
            with contextlib.suppress(TimeoutError):
                await asyncio.wait_for(self._kick.wait(), timeout=self.interval)

    def start(self) -> None:
        self._task = asyncio.create_task(self.run(), name="journal")

    async def stop(self) -> None:
        if self._task:
            self._task.cancel()
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await self._task


__all__ = ["JournalService", "Timeframe"]
