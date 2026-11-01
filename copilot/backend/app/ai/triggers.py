"""Decides *when* market conditions changed enough to be worth an AI comment.

Calling a language model on every tick would be slow and expensive. Instead
the deterministic analysis is diffed against what was seen before, and only
meaningful changes become triggers. Each trigger has a key so the same
condition never fires twice in a row.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

EVENT_TFS = ("1m", "5m", "15m")
TREND_TFS = ("5m", "15m", "1h")

EVENT_TEXT = {
    "bos_up": "strukturbrudd opp",
    "bos_down": "strukturbrudd ned",
    "breakout_up": "brudd over nivå",
    "breakout_down": "brudd under nivå",
    "false_breakout_up": "falskt brudd over nivå",
    "false_breakout_down": "falskt brudd under nivå",
}
TREND_TEXT = {"up": "opptrend", "down": "nedtrend", "sideways": "sideveis"}


@dataclass(frozen=True)
class Trigger:
    key: str
    reason: str  # Norwegian, shown in the panel and sent to the model
    priority: int  # higher = more important


class TriggerDetector:
    def __init__(self) -> None:
        self._seen_events: set[str] = set()
        self._trend: dict[str, str] = {}
        self._rsi_zone: str | None = None
        self._spread_high = False
        self._near_level: str | None = None
        self._primed = False

    def detect(self, analysis: dict[str, Any]) -> list[Trigger]:
        """Return new triggers. The first call only records the baseline."""
        out: list[Trigger] = []
        tfs = analysis.get("timeframes", {})

        for e in analysis.get("recentEvents", []):
            key = f"ev:{e['tf']}:{e['type']}:{e['t']}:{e['level']}"
            if key in self._seen_events:
                continue
            self._seen_events.add(key)
            if self._primed and e["tf"] in EVENT_TFS:
                prio = {"1m": 1, "5m": 2, "15m": 3}[e["tf"]]
                out.append(
                    Trigger(key, f"{e['tf']}: {EVENT_TEXT.get(e['type'], e['type'])} {e['level']}", prio)
                )

        for tf in TREND_TFS:
            a = tfs.get(tf) or {}
            if a.get("insufficient") or "trend" not in a:
                continue
            label = a["trend"]["label"]
            prev = self._trend.get(tf)
            self._trend[tf] = label
            if self._primed and prev is not None and prev != label:
                out.append(Trigger(f"trend:{tf}:{label}", f"{tf}-trenden skiftet til {TREND_TEXT[label]}", 3))

        a5 = tfs.get("5m") or {}
        zone = a5.get("rsiZone")
        if zone in ("overbought", "oversold") and zone != self._rsi_zone and self._primed:
            text = "overkjøpt" if zone == "overbought" else "oversolgt"
            out.append(Trigger(f"rsi5:{zone}", f"RSI 5m er {text} ({a5.get('rsi')})", 2))
        self._rsi_zone = zone

        spread = analysis.get("spread") or {}
        high = spread.get("state") == "high"
        if high and not self._spread_high and self._primed:
            out.append(Trigger("spread:high", f"spreaden er uvanlig høy ({spread.get('current')})", 2))
        self._spread_high = high

        near = self._nearest_strong_level(analysis)
        if near and near != self._near_level and self._primed:
            out.append(Trigger(f"level:{near}", f"prisen nærmer seg et viktig nivå ({near})", 2))
        self._near_level = near

        self._primed = True
        return out

    @staticmethod
    def _nearest_strong_level(analysis: dict[str, Any]) -> str | None:
        price = (analysis.get("price") or {}).get("bid")
        a5 = (analysis.get("timeframes") or {}).get("5m") or {}
        atr = a5.get("atr")
        if price is None or not atr or a5.get("insufficient"):
            return None
        levels = a5.get("levels", {})
        for lv in levels.get("support", []) + levels.get("resistance", []):
            if lv["touches"] >= 2 and abs(lv["price"] - price) <= 0.25 * atr:
                return f"{lv['price']}"
        return None
