"""Market conditions at the moment a trade was opened (deterministic).

Live trades get the analysis that was on screen when the monitor first saw
the position. Imported/historical trades are reconstructed from MT5 bars that
had *closed before* the entry time, so the context never includes data the
trader could not have seen.
"""

from __future__ import annotations

from typing import Any

from ..analysis.engine import analyze_timeframe
from ..market.models import Candle, SymbolSpec, Timeframe

TFS = (Timeframe.M1, Timeframe.M5, Timeframe.M15, Timeframe.H1)


def compact_context(analysis: dict[str, Any], direction: str | None = None) -> dict[str, Any]:
    tfs = {}
    for k, a in (analysis.get("timeframes") or {}).items():
        if not a or a.get("insufficient"):
            continue
        tfs[k] = {
            "trend": a["trend"]["label"],
            "score": a["trend"]["score"],
            "rsi": a.get("rsi"),
            "atr": a.get("atr"),
            "atrPct": a.get("atrPercentile"),
            "volatility": a.get("volatility"),
            "emaStack": a.get("emaStack"),
            "structure": (a.get("structure") or {}).get("label"),
            "distEma20Atr": a.get("distEma20Atr"),
        }
    ctx: dict[str, Any] = {"tf": tfs}
    spread = analysis.get("spread") or {}
    if spread.get("current") is not None:
        ctx["spread"] = spread["current"]
        ctx["spreadState"] = spread.get("state")
    if direction:
        ctx.update(alignment_flags(tfs, direction))
    return ctx


def alignment_flags(tfs: dict[str, Any], direction: str) -> dict[str, Any]:
    want = "up" if direction == "long" else "down"
    against = "down" if direction == "long" else "up"
    out = {}
    for k in ("5m", "15m", "1h"):
        if k in tfs:
            lab = tfs[k]["trend"]
            out[f"with{k}"] = "with" if lab == want else "against" if lab == against else "neutral"
    return out


def context_from_bars(
    bars: dict[Timeframe, list[Candle]], spec: SymbolSpec, direction: str, volume: float
) -> dict[str, Any]:
    tfs: dict[str, Any] = {}
    for tf in TFS:
        candles = bars.get(tf) or []
        if not candles:
            continue
        a = analyze_timeframe(tf, candles, spec)
        if a.get("insufficient"):
            continue
        tfs[tf.value] = {
            "trend": a["trend"]["label"],
            "score": a["trend"]["score"],
            "rsi": a.get("rsi"),
            "atr": a.get("atr"),
            "atrPct": a.get("atrPercentile"),
            "volatility": a.get("volatility"),
            "emaStack": a.get("emaStack"),
            "structure": (a.get("structure") or {}).get("label"),
            "distEma20Atr": a.get("distEma20Atr"),
        }
    ctx: dict[str, Any] = {"tf": tfs, **alignment_flags(tfs, direction)}
    m1 = bars.get(Timeframe.M1) or []
    if m1:
        spread = m1[-1].max_spread  # spread recorded on the last closed minute before entry
        ctx["spread"] = round(spread, spec.digits)
        ctx["spreadCost"] = round(spread * spec.contract_size * volume, 2)
    return ctx
