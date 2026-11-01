"""Compare the current market with the conditions of past trades (k nearest neighbours)."""

from __future__ import annotations

import math
from typing import Any

from ..journal.stats import bootstrap_ci, outcome, wilson
from ..sessions import SESSIONS


def features(ctx: dict[str, Any], session: str | None) -> list[float] | None:
    tf = (ctx or {}).get("tf") or {}
    if "5m" not in tf or "15m" not in tf:
        return None

    def g(k: str, f: str, scale: float, default: float = 0.0) -> float:
        v = (tf.get(k) or {}).get(f)
        return default if v is None else float(v) / scale

    return [
        g("1m", "score", 4),
        g("5m", "score", 4),
        g("15m", "score", 4),
        g("1h", "score", 4),
        g("1m", "rsi", 100, 0.5),
        g("5m", "rsi", 100, 0.5),
        g("1m", "atrPct", 100, 0.5),
        g("5m", "distEma20Atr", 3),
        # stable (not hash()-based, which is randomised per process)
        (SESSIONS.index(session) / len(SESSIONS)) if session in SESSIONS else 0.5,
    ]


def similar_trades(
    current_ctx: dict[str, Any], session: str, trades: list[dict[str, Any]], direction: str, k: int = 15
) -> dict[str, Any]:
    cur = features(current_ctx, session)
    if cur is None:
        return {"n": 0, "reason": "for lite analysedata"}
    scored = []
    for t in trades:
        if not t.get("closed") or t["direction"] != direction:
            continue
        f = features(t.get("context") or {}, t.get("session"))
        if f is None:
            continue
        scored.append((math.dist(cur, f), t))
    scored.sort(key=lambda x: x[0])
    near = [t for _, t in scored[:k]]
    if not near:
        return {"n": 0, "reason": "ingen tidligere handler med kontekst i denne retningen"}
    wins = sum(1 for t in near if t["net"] > 0)
    vals = [outcome(t) for t in near]
    return {
        "n": len(near),
        "direction": direction,
        "winRate": round(wins / len(near), 3),
        "winRateCi": wilson(wins, len(near)),
        "meanOutcome": round(sum(vals) / len(vals), 3),
        "meanCi": bootstrap_ci(vals),
        "unit": "R" if all(t.get("r_multiple") is not None for t in near) else "money",
        "examples": [
            {
                "position_id": t["position_id"],
                "open_ms": t["open_ms"],
                "net": t["net"],
                "r": t.get("r_multiple"),
            }
            for t in near[:5]
        ],
        "enough": len(near) >= 10,
    }
