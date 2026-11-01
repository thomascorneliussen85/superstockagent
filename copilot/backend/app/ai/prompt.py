"""What the language model sees, and the exact shape it must answer in.

The model never sees raw ticks. It gets a compact JSON snapshot of the
deterministic analysis (the facts) and is asked to interpret them in
Norwegian. Numbers in its answer are checked afterwards (see validate.py).
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from zoneinfo import ZoneInfo

from ..market.models import Candle, SymbolSpec, Tick

PROMPT_VERSION = "3.1.0"
OSLO = ZoneInfo("Europe/Oslo")

SYSTEM_PROMPT = """\
You are the market-analysis voice of a trading copilot for one person who scalps gold (XAUUSD) \
manually on the 1-minute chart and uses 5m, 15m and 1h for context. Everything you write is shown \
in a small panel next to their chart while they trade, so it must be short, concrete and in \
Norwegian (bokmål).

You receive a JSON snapshot of facts computed by deterministic code: price, spread, indicators \
(EMA 9/20/50/200, RSI 14, ATR 14, Supertrend 10/3), swing structure, support/resistance levels \
with touch counts, liquidity zones (equal highs/lows), candlestick patterns, recent breakouts and \
false breakouts, the trading session, and the reasons this update was triggered. Treat the \
snapshot as the only source of truth: use its numbers, do not invent prices or indicators that \
are not in it, and do not claim knowledge of news.

Write `summary` as 1-3 sentences a trader can absorb in two seconds, e.g.: "Gull er i en opptrend \
på 5m og 15m. RSI er 57 og prisen har trukket seg tilbake mot EMA 20. Et mulig long-oppsett \
utvikler seg, men bekreftelse mangler ennå." Mention what changed (the trigger) when it matters.

`bias` is your reading of the current conditions, not a forecast: "long" or "short" when the \
evidence leans clearly one way across timeframes, "neutral" when it is mixed, "avoid" when \
conditions are poor for scalping (very high spread, chaotic volatility, stale data, or strongly \
conflicting timeframes).

Only describe a `setup` (direction "long" or "short") when at least two independent facts in the \
snapshot support it, for example trend alignment plus a pullback to a level or EMA, or a \
confirmed breakout plus structure. Anchor every number to the snapshot: the entry zone near the \
current price at a level/EMA, the invalidation beyond the swing point or level that would prove \
the idea wrong (for a long below the entry, for a short above it), and the target at the next \
opposing level or liquidity zone. Account for the spread. Otherwise set direction to "none", kind \
to "none" and the four prices to 0. List the evidence for and against in `supporting` and \
`conflicting` (short Norwegian phrases), and put risks such as high spread, a nearby opposing \
level, low volume or an upcoming session change in `warnings`.

If `open_positions` is present, the trader already holds those gold positions: take them \
into account (for example, mention when the market structure now argues against an open \
position) but never tell them to close, add to or move anything; that is their decision.

Speak in possibilities ("mulig", "kan"), never certainties. Never promise profit or say a trade \
will work. You are not giving financial advice; the trader decides and executes everything \
themselves.\
"""

# Versioned system prompts. Every stored AI comment records the version used, so
# results can be compared per version and a worse version rolled back with
# COPILOT_AI_PROMPT_VERSION=<older version>.
_POSITIONS_START = SYSTEM_PROMPT.index("If `open_positions`")
_POSITIONS_END = SYSTEM_PROMPT.index("Speak in possibilities")
PROMPTS: dict[str, str] = {
    "3.0.0": SYSTEM_PROMPT[:_POSITIONS_START] + SYSTEM_PROMPT[_POSITIONS_END:],
    "3.1.0": SYSTEM_PROMPT,
}
LATEST_PROMPT_VERSION = PROMPT_VERSION


def prompt_for(version: str | None) -> tuple[str, str]:
    v = version if version in PROMPTS else LATEST_PROMPT_VERSION
    return v, PROMPTS[v]


OUTPUT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "summary": {"type": "string"},
        "bias": {"type": "string", "enum": ["long", "short", "neutral", "avoid"]},
        "setup": {
            "type": "object",
            "properties": {
                "direction": {"type": "string", "enum": ["long", "short", "none"]},
                "kind": {"type": "string", "enum": ["pullback", "breakout", "reversal", "range", "none"]},
                "entry_low": {"type": "number"},
                "entry_high": {"type": "number"},
                "invalidation": {"type": "number"},
                "target": {"type": "number"},
                "supporting": {"type": "array", "items": {"type": "string"}},
                "conflicting": {"type": "array", "items": {"type": "string"}},
            },
            "required": [
                "direction",
                "kind",
                "entry_low",
                "entry_high",
                "invalidation",
                "target",
                "supporting",
                "conflicting",
            ],
            "additionalProperties": False,
        },
        "warnings": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["summary", "bias", "setup", "warnings"],
    "additionalProperties": False,
}


def trading_session(dt: datetime) -> str:
    h = dt.astimezone(UTC).hour
    if 7 <= h < 12:
        return "London"
    if 12 <= h < 16:
        return "London/New York overlap"
    if 16 <= h < 21:
        return "New York"
    if 21 <= h < 23:
        return "late New York / rollover (often wide spreads)"
    return "Asia"


def _tf_facts(a: dict[str, Any]) -> dict[str, Any]:
    if a.get("insufficient"):
        return {"insufficient_data": True}
    lv = a.get("levels", {})
    liq = a.get("liquidity", {})
    st = a.get("structure", {})
    return {
        "trend": a["trend"]["label"],
        "trend_votes": a["trend"]["votes"],
        "ema": a.get("ema"),
        "ema_stack": a.get("emaStack"),
        "rsi": a.get("rsi"),
        "rsi_prev": a.get("rsiPrev"),
        "atr": a.get("atr"),
        "volatility": a.get("volatility"),
        "supertrend": a.get("supertrend"),
        "price_vs_ema20_in_atr": a.get("distEma20Atr"),
        "structure": {k: st.get(k) for k in ("label", "highs", "lows", "lastHigh", "lastLow")},
        "support": [(x["price"], x["touches"]) for x in lv.get("support", [])[:2]],
        "resistance": [(x["price"], x["touches"]) for x in lv.get("resistance", [])[:2]],
        "liquidity_above": [x["price"] for x in liq.get("above", [])[:2]],
        "liquidity_below": [x["price"] for x in liq.get("below", [])[:2]],
        "patterns_last_closed": a.get("patterns", []),
        "tick_volume_vs_avg": a.get("tickVolumeRatio"),
    }


def _candles(candles: list[Candle], n: int, digits: int) -> list[list[float]]:
    return [
        [round(c.open, digits), round(c.high, digits), round(c.low, digits), round(c.close, digits)]
        for c in candles[-n:]
    ]


def build_snapshot(
    analysis: dict[str, Any],
    spec: SymbolSpec,
    tick: Tick | None,
    candles_1m: list[Candle],
    candles_5m: list[Candle],
    triggers: list[str],
    now: datetime,
) -> dict[str, Any]:
    d = spec.digits
    spread = analysis.get("spread") or {}
    return {
        "symbol": spec.symbol,
        "time_oslo": now.astimezone(OSLO).strftime("%Y-%m-%d %H:%M"),
        "session": trading_session(now),
        "update_reasons": triggers,
        "price": None if tick is None else {"bid": round(tick.bid, d), "ask": round(tick.ask, d)},
        "spread": {
            "now": spread.get("current"),
            "median": spread.get("median"),
            "state": spread.get("state"),
        },
        "contract_oz_per_lot": spec.contract_size,
        "timeframes": {k: _tf_facts(v) for k, v in analysis.get("timeframes", {}).items()},
        "last_1m_candles_ohlc": _candles(candles_1m, 6, d),
        "last_5m_candles_ohlc": _candles(candles_5m, 4, d),
        "recent_events": [
            {"tf": e["tf"], "type": e["type"], "level": e["level"]}
            for e in analysis.get("recentEvents", [])[:5]
        ],
    }
