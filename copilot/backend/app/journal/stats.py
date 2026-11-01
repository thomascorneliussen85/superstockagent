"""Performance statistics over closed trades (pure, deterministic).

Statistical helpers (Wilson interval, bootstrap) live here too so the journal
and the coach use exactly the same maths.
"""

from __future__ import annotations

import math
import random
from collections import defaultdict
from collections.abc import Callable, Sequence
from typing import Any

from ..sessions import SESSIONS, oslo

WEEKDAYS = ["Man", "Tir", "Ons", "Tor", "Fre", "Lør", "Søn"]


# ---- statistics helpers ----------------------------------------------------------
def wilson(successes: int, n: int, z: float = 1.96) -> tuple[float, float] | None:
    if n <= 0:
        return None
    p = successes / n
    den = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / den
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / den
    return max(0.0, centre - half), min(1.0, centre + half)


def bootstrap_ci(
    values: Sequence[float], stat: Callable[[Sequence[float]], float] = None, iters: int = 2000, seed: int = 7
) -> tuple[float, float] | None:
    """95 % percentile bootstrap interval of ``stat`` (default: mean)."""
    if len(values) < 2:
        return None
    stat = stat or (lambda xs: sum(xs) / len(xs))
    rng = random.Random(seed)
    n = len(values)
    samples = sorted(stat([values[rng.randrange(n)] for _ in range(n)]) for _ in range(iters))
    return samples[int(0.025 * iters)], samples[int(0.975 * iters) - 1]


def bootstrap_diff_ci(
    a: Sequence[float], b: Sequence[float], iters: int = 2000, seed: int = 11
) -> tuple[float, float] | None:
    """95 % bootstrap interval for mean(a) - mean(b)."""
    if len(a) < 2 or len(b) < 2:
        return None
    rng = random.Random(seed)
    na, nb = len(a), len(b)
    diffs = sorted(
        sum(a[rng.randrange(na)] for _ in range(na)) / na - sum(b[rng.randrange(nb)] for _ in range(nb)) / nb
        for _ in range(iters)
    )
    return diffs[int(0.025 * iters)], diffs[int(0.975 * iters) - 1]


# ---- per-group metrics --------------------------------------------------------------
def outcome(t: dict[str, Any]) -> float:
    """Metric used for comparisons: R multiple when known, else net money."""
    return t["r_multiple"] if t.get("r_multiple") is not None else t["net"]


def group_metrics(trades: Sequence[dict[str, Any]]) -> dict[str, Any]:
    n = len(trades)
    if n == 0:
        return {"n": 0}
    nets = [t["net"] for t in trades]
    wins = [x for x in nets if x > 0]
    losses = [x for x in nets if x < 0]
    rs = [t["r_multiple"] for t in trades if t.get("r_multiple") is not None]
    gl = -sum(losses)
    return {
        "n": n,
        "net": round(sum(nets), 2),
        "avgNet": round(sum(nets) / n, 2),
        "winRate": round(len(wins) / n, 4),
        "profitFactor": None if gl == 0 else round(sum(wins) / gl, 2),
        "avgR": None if not rs else round(sum(rs) / len(rs), 3),
        "nR": len(rs),
    }


def _streaks(nets: Sequence[float]) -> dict[str, Any]:
    best_w = best_l = cur = 0
    for x in nets:
        if x > 0:
            cur = cur + 1 if cur > 0 else 1
        elif x < 0:
            cur = cur - 1 if cur < 0 else -1
        else:
            cur = 0
        best_w, best_l = max(best_w, cur), max(best_l, -cur)
    return {"maxWins": best_w, "maxLosses": best_l, "current": cur}


def compute_stats(trades: Sequence[dict[str, Any]]) -> dict[str, Any]:
    trades = sorted((t for t in trades if t.get("closed")), key=lambda t: t["close_ms"] or t["open_ms"])
    n = len(trades)
    base = group_metrics(trades)
    if n == 0:
        return {"summary": base, "empty": True}
    nets = [t["net"] for t in trades]
    wins = [x for x in nets if x > 0]
    losses = [x for x in nets if x < 0]
    rs = [t["r_multiple"] for t in trades if t.get("r_multiple") is not None]

    # Equity & drawdown on closed-trade results
    equity, peak, max_dd = [], 0.0, 0.0
    cum = 0.0
    for t in trades:
        cum += t["net"]
        peak = max(peak, cum)
        max_dd = max(max_dd, peak - cum)
        equity.append({"t": t["close_ms"], "equity": round(cum, 2), "drawdown": round(cum - peak, 2)})

    daily: dict[str, float] = defaultdict(float)
    for t in trades:
        daily[oslo(t["close_ms"]).strftime("%Y-%m-%d")] += t["net"]

    def by(key: Callable[[dict[str, Any]], Any], order: Sequence[Any] | None = None) -> list[dict[str, Any]]:
        groups: dict[Any, list[dict[str, Any]]] = defaultdict(list)
        for t in trades:
            groups[key(t)].append(t)
        keys = [k for k in order if k in groups] if order else sorted(groups, key=lambda k: (k is None, k))
        return [{"key": k, **group_metrics(groups[k])} for k in keys]

    costs = {
        "commission": round(sum(t["commission"] for t in trades), 2),
        "swap": round(sum(t["swap"] for t in trades), 2),
        "fee": round(sum(t["fee"] for t in trades), 2),
    }
    spread_est = [
        (t["context"] or {}).get("spreadCost")
        for t in trades
        if t.get("context") and t["context"].get("spreadCost")
    ]
    costs["spreadEstimate"] = round(sum(spread_est), 2) if spread_est else None
    costs["total"] = round(costs["commission"] + costs["swap"] + costs["fee"], 2)

    hist = defaultdict(int)
    use_r = len(rs) >= max(5, n // 2)
    for t in trades:
        v = t["r_multiple"] if use_r and t.get("r_multiple") is not None else (None if use_r else t["net"])
        if v is None:
            continue
        step = 0.5 if use_r else max(1.0, round((max(map(abs, nets)) or 1) / 8, 0))
        hist[math.floor(v / step) * step] += 1

    wr = len(wins) / n
    return {
        "empty": False,
        "summary": {
            **base,
            "wins": len(wins),
            "losses": len(losses),
            "winRateCi": wilson(len(wins), n),
            "grossProfit": round(sum(wins), 2),
            "grossLoss": round(sum(losses), 2),
            "avgWin": None if not wins else round(sum(wins) / len(wins), 2),
            "avgLoss": None if not losses else round(sum(losses) / len(losses), 2),
            "expectancy": round(sum(nets) / n, 2),
            "expectancyCi": bootstrap_ci(nets),
            "expectancyR": None if not rs else round(sum(rs) / len(rs), 3),
            "expectancyRCi": bootstrap_ci(rs) if len(rs) >= 2 else None,
            "maxDrawdown": round(max_dd, 2),
            "streaks": _streaks(nets),
            "avgDurationMin": round(sum((t["close_ms"] - t["open_ms"]) for t in trades) / n / 60000, 1),
            "winRatePct": round(100 * wr, 1),
            "firstMs": trades[0]["open_ms"],
            "lastMs": trades[-1]["close_ms"],
        },
        "costs": costs,
        "equity": equity,
        "daily": [{"day": d, "net": round(v, 2)} for d, v in sorted(daily.items())],
        "byHour": by(lambda t: oslo(t["open_ms"]).hour),
        "byWeekday": [{**g, "key": WEEKDAYS[g["key"]]} for g in by(lambda t: oslo(t["open_ms"]).weekday())],
        "bySession": by(lambda t: t["session"], SESSIONS),
        "bySetup": by(lambda t: t.get("setup") or "(uten tag)"),
        "byDirection": by(lambda t: t["direction"], ["long", "short"]),
        "distribution": {
            "unit": "R" if use_r else "money",
            "bins": [{"from": k, "count": c} for k, c in sorted(hist.items())],
        },
    }
