"""Evaluates past AI setups against what the market did afterwards.

This is a hypothetical, after-the-fact check of the *idea* (did price reach
the target or the invalidation first?), done with 1-minute bars recorded after
the comment. It measures the accuracy of the AI's suggestions; it says
nothing about whether following them caused any trade result.
"""

from __future__ import annotations

from collections import defaultdict
from typing import Any

from ..journal.stats import bootstrap_ci, wilson
from ..market.models import Candle

TRIGGER_WINDOW = 30  # minutes for price to reach the entry zone
HORIZON = 240  # minutes after the trigger before the idea is closed at market


def evaluate_setup(setup: dict[str, Any], created_ms: int, bars: list[Candle], now_ms: int) -> dict[str, Any]:
    long = setup["direction"] == "long"
    lo, hi = setup["entryLow"], setup["entryHigh"]
    inv, tgt = setup["invalidation"], setup["target"]
    spread = setup.get("spreadAtCheck") or 0.0
    entry = (lo + hi) / 2
    risk = abs(entry - inv) + spread
    after = [b for b in sorted(bars, key=lambda b: b.open_time_ms) if b.open_time_ms >= created_ms]
    trig_idx = None
    for i, b in enumerate(after[:TRIGGER_WINDOW]):
        if b.low <= hi and b.high >= lo:
            trig_idx = i
            break
    if trig_idx is None:
        done = now_ms - created_ms >= TRIGGER_WINDOW * 60_000 and len(after) >= TRIGGER_WINDOW
        return {"status": "not_triggered" if done else "pending"}
    for b in after[trig_idx : trig_idx + HORIZON]:
        if long:
            hit_inv, hit_tgt = b.low <= inv, b.high >= tgt
        else:  # a short is closed at the ask = bid + spread
            hit_inv, hit_tgt = b.high + spread >= inv, b.low + spread <= tgt
        if hit_inv and hit_tgt:
            return {"status": "ambiguous", "triggeredAt": after[trig_idx].open_time_ms}
        if hit_tgt:
            return {
                "status": "target",
                "r": setup.get("rr"),
                "triggeredAt": after[trig_idx].open_time_ms,
                "resolvedAt": b.open_time_ms,
            }
        if hit_inv:
            return {
                "status": "invalidation",
                "r": -1.0,
                "triggeredAt": after[trig_idx].open_time_ms,
                "resolvedAt": b.open_time_ms,
            }
    window = after[trig_idx : trig_idx + HORIZON]
    if len(window) >= HORIZON:
        last = window[-1].close
        move = (last - entry - spread) if long else (entry - last - spread)
        return {"status": "expired", "r": round(move / risk, 3) if risk > 0 else 0.0}
    return {"status": "open", "triggeredAt": after[trig_idx].open_time_ms}


def summarize_outcomes(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """rows: {status, r, bias, kind, promptVersion, link}"""

    def block(rs: list[dict[str, Any]]) -> dict[str, Any]:
        resolved = [r for r in rs if r["status"] in ("target", "invalidation")]
        hits = sum(1 for r in resolved if r["status"] == "target")
        vals = [r["r"] for r in rs if r.get("r") is not None]
        return {
            "setups": len(rs),
            "resolved": len(resolved),
            "hitRate": None if not resolved else round(hits / len(resolved), 3),
            "hitRateCi": wilson(hits, len(resolved)),
            "meanR": None if not vals else round(sum(vals) / len(vals), 3),
            "meanRCi": bootstrap_ci(vals) if len(vals) >= 2 else None,
            "notTriggered": sum(1 for r in rs if r["status"] == "not_triggered"),
            "ambiguous": sum(1 for r in rs if r["status"] == "ambiguous"),
        }

    def grouped(key: str) -> dict[str, Any]:
        g: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for r in rows:
            g[str(r.get(key))].append(r)
        return {k: block(v) for k, v in sorted(g.items())}

    return {
        "all": block(rows),
        "byDirection": grouped("direction"),
        "byKind": grouped("kind"),
        "byPromptVersion": grouped("promptVersion"),
        "byFollow": grouped("link"),
        "note": "Treffsikkerheten gjelder AI-ens forslag i seg selv. Om du fulgte et forslag er registrert, "
        "men det betyr ikke at forslaget forårsaket resultatet.",
    }
