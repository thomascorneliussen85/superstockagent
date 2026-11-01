"""Combines indicators and structure into one deterministic market snapshot.

This is the *factual* layer. It contains no predictions and no language
model. Phase 3 hands a compact form of this snapshot to the LLM, which only
explains it.

Indicator values include the still-forming candle (like the live chart).
Structure, levels, patterns and events use closed candles only.
"""

from __future__ import annotations

import statistics
from collections.abc import Sequence
from typing import Any

from ..market.models import Candle, SymbolSpec, Tick, Timeframe
from . import indicators as ind
from .structure import (
    classify_structure,
    cluster_levels,
    detect_patterns,
    find_swings,
    level_events,
    nearest_levels,
    structure_break,
)

EMA_PERIODS = (9, 20, 50, 200)
RSI_PERIOD = 14
ATR_PERIOD = 14
ST_FACTOR, ST_PERIOD = 3.0, 10
SWING_LOOKBACK = 300  # closed bars used for levels
MIN_BARS = 30  # below this a timeframe is reported as insufficient

ENGINE_VERSION = "2.0.0"


def _r(v: float | None, d: int) -> float | None:
    return None if v is None else round(v, d)


def rsi_zone(v: float | None) -> str | None:
    if v is None:
        return None
    if v >= 70:
        return "overbought"
    if v <= 30:
        return "oversold"
    if v >= 55:
        return "bullish"
    if v <= 45:
        return "bearish"
    return "neutral"


def ema_stack(e9: float | None, e20: float | None, e50: float | None) -> str | None:
    if None in (e9, e20, e50):
        return None
    if e9 > e20 > e50:  # type: ignore[operator]
        return "bull"
    if e9 < e20 < e50:  # type: ignore[operator]
        return "bear"
    return "mixed"


def trend_votes(stack: str | None, st_dir: int | None, struct: str, above200: bool | None) -> dict[str, int]:
    """Four independent trend votes, each -1/0/+1. The rule is documented and fixed."""
    return {
        "ema": {"bull": 1, "bear": -1}.get(stack or "", 0),
        "supertrend": st_dir or 0,
        "structure": {"bullish": 1, "bearish": -1}.get(struct, 0),
        "ema200": 0 if above200 is None else (1 if above200 else -1),
    }


def trend_label(score: int) -> str:
    if score >= 2:
        return "up"
    if score <= -2:
        return "down"
    return "sideways"


def analyze_timeframe(
    tf: Timeframe, candles: Sequence[Candle], spec: SymbolSpec, price: float | None = None
) -> dict[str, Any]:
    d = spec.digits
    closed = [c for c in candles if c.closed]
    result: dict[str, Any] = {"tf": tf.value, "bars": len(candles), "closedBars": len(closed)}
    if len(candles) < MIN_BARS:
        result["insufficient"] = True
        return result
    result["insufficient"] = False

    highs = [c.high for c in candles]
    lows = [c.low for c in candles]
    closes = [c.close for c in candles]
    last = candles[-1]
    price = price if price is not None else last.close

    emas = {n: ind.ema(closes, n)[-1] for n in EMA_PERIODS}
    rsi_series = ind.rsi(closes, RSI_PERIOD)
    atr_series = ind.atr(highs, lows, closes, ATR_PERIOD)
    st_line, st_dir = ind.supertrend(highs, lows, closes, ST_FACTOR, ST_PERIOD)
    atr_now = atr_series[-1]
    rsi_now = rsi_series[-1]

    # --- structure & levels on closed bars -------------------------------
    window = closed[-SWING_LOOKBACK:]
    swings = find_swings(window)
    structure = classify_structure(swings)
    tol = max((atr_now or 0) * 0.3, 10 * spec.point)
    levels = cluster_levels(swings, tol)
    supports, resistances = nearest_levels(levels, price)
    atr_closed = ind.atr([c.high for c in closed], [c.low for c in closed], [c.close for c in closed])
    atr_closed_now = atr_closed[-1] if atr_closed else None
    patterns = detect_patterns(closed, atr_closed_now)

    events: list[dict] = []
    bos = structure_break(closed, structure)
    if bos:
        events.append(bos)
    near = [lv for lv in levels if lv.touches >= 2]
    events.extend(level_events(closed, near, d))
    last_closed_t = closed[-1].open_time_ms if closed else None
    for e in events:
        e["tf"] = tf.value
        e["t"] = last_closed_t

    liq_above = [lv for lv in levels if lv.highs >= 2 and lv.price > price]
    liq_below = [lv for lv in levels if lv.lows >= 2 and lv.price < price]
    liq_above.sort(key=lambda lv: lv.price - price)
    liq_below.sort(key=lambda lv: price - lv.price)

    # --- trend -------------------------------------------------------------
    stack = ema_stack(emas[9], emas[20], emas[50])
    above200 = None if emas[200] is None else price > emas[200]
    votes = trend_votes(stack, st_dir[-1], structure["label"], above200)
    score = sum(votes.values())

    # --- volatility & volume ------------------------------------------------
    atr_pct = ind.percentile_rank(atr_series[-100:], atr_now) if atr_now is not None else None
    vol_label = None
    if atr_pct is not None:
        vol_label = "high" if atr_pct >= 80 else "low" if atr_pct <= 20 else "normal"
    tick_counts = [c.tick_count for c in closed[-21:-1]]
    vol_ratio = None
    if closed and tick_counts and statistics.mean(tick_counts) > 0:
        vol_ratio = closed[-1].tick_count / statistics.mean(tick_counts)

    dist20 = None
    if emas[20] is not None and atr_now:
        dist20 = (price - emas[20]) / atr_now

    result.update(
        {
            "lastClosedT": last_closed_t,
            "formingT": last.open_time_ms if not last.closed else None,
            "close": _r(last.close, d),
            "ema": {str(n): _r(v, d) for n, v in emas.items()},
            "emaStack": stack,
            "aboveEma200": above200,
            "rsi": _r(rsi_now, 1),
            "rsiPrev": _r(rsi_series[-2] if len(rsi_series) > 1 else None, 1),
            "rsiZone": rsi_zone(rsi_now),
            "atr": _r(atr_now, d),
            "atrPercentile": _r(atr_pct, 0),
            "volatility": vol_label,
            "lastRangeAtr": _r((last.high - last.low) / atr_now, 2) if atr_now else None,
            "supertrend": {"dir": st_dir[-1], "value": _r(st_line[-1], d)},
            "distEma20Atr": _r(dist20, 2),
            "structure": {
                **structure,
                "lastHigh": _r(structure["lastHigh"], d),
                "lastLow": _r(structure["lastLow"], d),
            },
            "trend": {"label": trend_label(score), "score": score, "votes": votes},
            "levels": {
                "support": [lv.to_wire(d) for lv in supports],
                "resistance": [lv.to_wire(d) for lv in resistances],
            },
            "liquidity": {
                "above": [lv.to_wire(d) for lv in liq_above[:3]],
                "below": [lv.to_wire(d) for lv in liq_below[:3]],
            },
            "patterns": patterns,
            "events": events,
            "tickVolumeRatio": _r(vol_ratio, 2),
        }
    )
    return result


def spread_stats(samples: Sequence[float], current: float | None, spec: SymbolSpec) -> dict[str, Any] | None:
    if current is None:
        return None
    d = spec.digits
    out: dict[str, Any] = {
        "current": round(current, d),
        "points": round(current / spec.point),
        # Cost of crossing the spread once, in profit currency per 1.0 lot.
        "costPerLot": round(current * spec.contract_size, 2),
        "currency": spec.currency_profit,
    }
    if len(samples) >= 50:
        med = statistics.median(samples)
        p90 = statistics.quantiles(samples, n=10)[-1]
        ratio = current / med if med > 0 else None
        out.update(
            {
                "median": round(med, d),
                "p90": round(p90, d),
                "ratio": None if ratio is None else round(ratio, 2),
                "state": None
                if ratio is None
                else "high"
                if ratio >= 2.5
                else "elevated"
                if ratio >= 1.5
                else "normal",
                "samples": len(samples),
            }
        )
    else:
        out["state"] = None
        out["samples"] = len(samples)
    return out


def analyze(
    candles_by_tf: dict[Timeframe, Sequence[Candle]],
    spec: SymbolSpec,
    tick: Tick | None,
    spread_samples: Sequence[float],
    now_ms: int,
) -> dict[str, Any]:
    price = tick.bid if tick else None
    tfs = {tf.value: analyze_timeframe(tf, c, spec, price) for tf, c in candles_by_tf.items()}
    labels = [v["trend"]["label"] for v in tfs.values() if not v.get("insufficient")]
    return {
        "engine": ENGINE_VERSION,
        "computedAt": now_ms,
        "tickTime": tick.time_ms if tick else None,
        "symbol": spec.symbol,
        "price": None if tick is None else {"bid": tick.bid, "ask": tick.ask},
        "timeframes": tfs,
        "alignment": {
            "up": labels.count("up"),
            "down": labels.count("down"),
            "sideways": labels.count("sideways"),
        },
        "spread": spread_stats(spread_samples, tick.spread if tick else None, spec),
    }
