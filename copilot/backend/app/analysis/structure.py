"""Market structure, support/resistance, liquidity and candlestick patterns.

Everything here works on *closed* candles only. A swing point needs
``right`` later bars to be confirmed, so nothing depends on future data
relative to the last closed bar.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from ..market.models import Candle


@dataclass(frozen=True, slots=True)
class Swing:
    index: int
    time_ms: int
    price: float
    kind: str  # "high" | "low"


def find_swings(candles: Sequence[Candle], left: int = 3, right: int = 3) -> list[Swing]:
    out: list[Swing] = []
    for i in range(left, len(candles) - right):
        c = candles[i]
        lh = [x.high for x in candles[i - left : i]]
        rh = [x.high for x in candles[i + 1 : i + 1 + right]]
        if c.high > max(lh) and c.high >= max(rh):
            out.append(Swing(i, c.open_time_ms, c.high, "high"))
        ll = [x.low for x in candles[i - left : i]]
        rl = [x.low for x in candles[i + 1 : i + 1 + right]]
        if c.low < min(ll) and c.low <= min(rl):
            out.append(Swing(i, c.open_time_ms, c.low, "low"))
    return out


def classify_structure(swings: Sequence[Swing]) -> dict:
    highs = [s for s in swings if s.kind == "high"]
    lows = [s for s in swings if s.kind == "low"]
    hi_label = lo_label = None
    if len(highs) >= 2:
        hi_label = "HH" if highs[-1].price > highs[-2].price else "LH"
    if len(lows) >= 2:
        lo_label = "HL" if lows[-1].price > lows[-2].price else "LL"
    if hi_label == "HH" and lo_label == "HL":
        label = "bullish"
    elif hi_label == "LH" and lo_label == "LL":
        label = "bearish"
    elif hi_label is None or lo_label is None:
        label = "unknown"
    else:
        label = "range"
    return {
        "label": label,
        "highs": hi_label,
        "lows": lo_label,
        "lastHigh": highs[-1].price if highs else None,
        "lastLow": lows[-1].price if lows else None,
        "lastHighT": highs[-1].time_ms if highs else None,
        "lastLowT": lows[-1].time_ms if lows else None,
    }


@dataclass(slots=True)
class Level:
    price: float
    touches: int
    highs: int
    lows: int
    last_time_ms: int

    def to_wire(self, digits: int) -> dict:
        return {
            "price": round(self.price, digits),
            "touches": self.touches,
            "highs": self.highs,
            "lows": self.lows,
            "lastT": self.last_time_ms,
        }


def cluster_levels(swings: Sequence[Swing], tolerance: float) -> list[Level]:
    """Group swing prices lying within ``tolerance`` of a cluster's mean."""
    levels: list[Level] = []
    sums: list[float] = []
    for s in sorted(swings, key=lambda x: x.price):
        if levels and abs(s.price - levels[-1].price) <= tolerance:
            lv = levels[-1]
            sums[-1] += s.price
            lv.touches += 1
            lv.price = sums[-1] / lv.touches
            lv.highs += s.kind == "high"
            lv.lows += s.kind == "low"
            lv.last_time_ms = max(lv.last_time_ms, s.time_ms)
        else:
            levels.append(Level(s.price, 1, int(s.kind == "high"), int(s.kind == "low"), s.time_ms))
            sums.append(s.price)
    return levels


def nearest_levels(levels: Sequence[Level], price: float, k: int = 3) -> tuple[list[Level], list[Level]]:
    """(supports below price nearest-first, resistances above price nearest-first)."""
    below = sorted((lv for lv in levels if lv.price < price), key=lambda lv: price - lv.price)
    above = sorted((lv for lv in levels if lv.price >= price), key=lambda lv: lv.price - price)
    return below[:k], above[:k]


def detect_patterns(candles: Sequence[Candle], atr_value: float | None) -> list[str]:
    """Candlestick patterns on the last closed candle."""
    if len(candles) < 2:
        return []
    c, p = candles[-1], candles[-2]
    rng = c.high - c.low
    if rng <= 0:
        return []
    body = abs(c.close - c.open)
    upper = c.high - max(c.open, c.close)
    lower = min(c.open, c.close) - c.low
    meaningful = atr_value is None or rng >= 0.5 * atr_value
    out: list[str] = []
    # Pin bars first: a long-wicked small body is a rejection, not indecision.
    if meaningful and lower >= 2 * body and lower >= 0.6 * rng and upper <= 0.25 * rng:
        out.append("bullish_pin")
    elif meaningful and upper >= 2 * body and upper >= 0.6 * rng and lower <= 0.25 * rng:
        out.append("bearish_pin")
    elif body <= 0.1 * rng:
        out.append("doji")
    p_body = abs(p.close - p.open)
    if p.close < p.open and c.close > c.open and c.open <= p.close and c.close >= p.open and body > p_body:
        out.append("bullish_engulfing")
    if p.close > p.open and c.close < c.open and c.open >= p.close and c.close <= p.open and body > p_body:
        out.append("bearish_engulfing")
    if c.high < p.high and c.low > p.low:
        out.append("inside_bar")
    return out


def level_events(candles: Sequence[Candle], levels: Sequence[Level], digits: int) -> list[dict]:
    """Breakouts and false breakouts (liquidity sweeps) on the last closed candle."""
    if len(candles) < 2:
        return []
    c, p = candles[-1], candles[-2]
    out: list[dict] = []
    for lv in levels:
        L = lv.price
        if p.close <= L < c.close:
            out.append({"type": "breakout_up", "level": round(L, digits)})
        elif p.close >= L > c.close:
            out.append({"type": "breakout_down", "level": round(L, digits)})
        elif c.high > L and c.close < L and p.close < L:
            out.append({"type": "false_breakout_up", "level": round(L, digits)})
        elif c.low < L and c.close > L and p.close > L:
            out.append({"type": "false_breakout_down", "level": round(L, digits)})
    return out


def structure_break(candles: Sequence[Candle], structure: dict) -> dict | None:
    """Break of structure: last close crosses the last confirmed swing high/low."""
    if len(candles) < 2:
        return None
    c, p = candles[-1], candles[-2]
    hi, lo = structure.get("lastHigh"), structure.get("lastLow")
    if hi is not None and p.close <= hi < c.close:
        return {"type": "bos_up", "level": hi}
    if lo is not None and p.close >= lo > c.close:
        return {"type": "bos_down", "level": lo}
    return None


def trendlines(
    candles: Sequence[Candle], swings: Sequence[Swing], atr: float | None, digits: int
) -> list[dict]:
    """Rising support through the last two higher swing lows, falling resistance
    through the last two lower swing highs. Closed candles only.

    ``valueNow`` is the line's price at the last candle; ``broken`` means the
    last close is on the wrong side of it.
    """
    if not candles or not atr:
        return []
    out: list[dict] = []
    last = candles[-1]
    for kind, pts_kind in (("support", "low"), ("resistance", "high")):
        pts = [s for s in swings if s.kind == pts_kind]
        if len(pts) < 2:
            continue
        a, b = pts[-2], pts[-1]
        rising = b.price > a.price
        if (kind == "support" and not rising) or (kind == "resistance" and rising) or b.time_ms == a.time_ms:
            continue
        slope = (b.price - a.price) / (b.time_ms - a.time_ms)

        def line_at(t: int, a: Swing = a, slope: float = slope) -> float:
            return a.price + slope * (t - a.time_ms)

        touches = 0
        violations = 0
        for c in candles[a.index :]:
            v = line_at(c.open_time_ms)
            probe = c.low if kind == "support" else c.high
            if abs(probe - v) <= 0.15 * atr:
                touches += 1
            if (kind == "support" and c.close < v - 0.1 * atr) or (
                kind == "resistance" and c.close > v + 0.1 * atr
            ):
                violations += 1
        now_v = line_at(last.open_time_ms)
        broken = (last.close < now_v) if kind == "support" else (last.close > now_v)
        if violations > 2 and not broken:
            continue  # sliced through repeatedly: not a meaningful line
        out.append(
            {
                "kind": kind,
                "t1": a.time_ms,
                "p1": round(a.price, digits),
                "t2": b.time_ms,
                "p2": round(b.price, digits),
                "tNow": last.open_time_ms,
                "valueNow": round(now_v, digits),
                "touches": touches,
                "broken": broken,
            }
        )
    return out


def volume_profile(
    candles: Sequence[Candle], bin_size: float, digits: int, value_area: float = 0.7
) -> dict | None:
    """Price histogram of *tick volume* (spot gold has no central exchange volume).

    Each candle's tick count is spread evenly over the price bins its range
    covers. Returns the point of control (POC), the value area (70 % of volume
    around the POC) and high-volume nodes (local peaks well above the median).
    """
    if not candles or bin_size <= 0:
        return None
    lo = min(c.low for c in candles)
    hi = max(c.high for c in candles)
    n = max(1, int((hi - lo) / bin_size) + 1)
    if n > 400:
        bin_size = (hi - lo) / 399
        n = 400
    vols = [0.0] * n
    for c in candles:
        i0 = int((c.low - lo) / bin_size)
        i1 = min(n - 1, int((c.high - lo) / bin_size))
        share = max(1, c.tick_count) / (i1 - i0 + 1)
        for i in range(i0, i1 + 1):
            vols[i] += share
    total = sum(vols)
    poc = max(range(n), key=lambda i: vols[i])
    a = b = poc
    acc = vols[poc]
    while acc < value_area * total and (a > 0 or b < n - 1):
        up = vols[b + 1] if b < n - 1 else -1
        dn = vols[a - 1] if a > 0 else -1
        if up >= dn:
            b += 1
            acc += up
        else:
            a -= 1
            acc += dn
    srt = sorted(vols)
    median = srt[n // 2]
    price = lambda i: round(lo + (i + 0.5) * bin_size, digits)  # noqa: E731
    hvn = [
        i
        for i in range(1, n - 1)
        if vols[i] >= vols[i - 1] and vols[i] >= vols[i + 1] and vols[i] >= 1.5 * median and i != poc
    ]
    hvn.sort(key=lambda i: -vols[i])
    peak = max(vols) or 1
    return {
        "binSize": round(bin_size, digits),
        "bins": [{"p": price(i), "v": round(vols[i] / peak, 3)} for i in range(n)],
        "poc": price(poc),
        "vah": round(lo + (b + 1) * bin_size, digits),
        "val": round(lo + a * bin_size, digits),
        "hvn": [price(i) for i in hvn[:3]],
        "bars": len(candles),
    }
