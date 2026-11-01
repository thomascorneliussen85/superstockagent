"""Polls the MT5 account once per second and publishes a risk view.

Read-only: the monitor only reads account_info, positions_get, orders_get and
history_deals_get through the market source. It never sends, modifies or
closes anything.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

from ..hub import MarketHub
from .risk import RiskRules, build_account_view

log = logging.getLogger(__name__)
OSLO = ZoneInfo("Europe/Oslo")


def oslo_day_start_utc_ms(now: datetime) -> int:
    local = now.astimezone(OSLO)
    return int(local.replace(hour=0, minute=0, second=0, microsecond=0).timestamp() * 1000)


class AccountMonitor:
    def __init__(
        self, hub: MarketHub, analysis: Any, rules: RiskRules, interval: float = 1.0, now: Any = None
    ) -> None:
        self.hub = hub
        self.analysis = analysis
        self.rules = rules
        self.interval = interval
        self._now = now or (lambda: datetime.now(OSLO))
        self.last: dict[str, Any] | None = None
        self._last_sent: Any = None
        self._task: asyncio.Task | None = None

    def _context(self) -> tuple[dict[str, float | None], set[str]]:
        a = self.analysis.last or {}
        atr = ((a.get("timeframes") or {}).get("1m") or {}).get("atr")
        sym = (
            self.hub.spec.broker_symbol if self.hub.spec and self.hub.spec.broker_symbol else self.hub.symbol
        )
        high = (a.get("spread") or {}).get("state") == "high"
        return {sym: atr, self.hub.symbol: atr}, ({sym} if high else set())

    async def step(self) -> None:
        source = self.hub.source
        snap_fn = getattr(source, "account_snapshot", None)
        if snap_fn is None:
            view: dict[str, Any] = {
                "available": False,
                "reason": "Posisjoner og risiko krever MT5 (backend kjører med demodata).",
            }
        else:
            raw = await snap_fn(oslo_day_start_utc_ms(self._now()))
            if raw is None:
                view = {"available": False, "reason": "Venter på MT5-kontoen …"}
            else:
                atr, spread_high = self._context()
                view = build_account_view(raw, self.rules, atr, spread_high)
        if view != self._last_sent:
            self._last_sent = view
            self.last = view
            self.hub.publish({"type": "account", "data": view}, retain=True)

    async def run(self) -> None:
        while True:
            try:
                await self.step()
            except Exception:  # noqa: BLE001 - monitoring must never take the feed down
                log.exception("Account monitor step failed")
            await asyncio.sleep(self.interval)

    def start(self) -> None:
        self._task = asyncio.create_task(self.run(), name="account")

    async def stop(self) -> None:
        if self._task:
            self._task.cancel()
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await self._task
