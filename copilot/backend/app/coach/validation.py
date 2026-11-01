"""Out-of-sample checks before anything is recommended, and drift detection.

* ``walk_forward``: a candidate rule (a filter on trades, e.g. "only with the
  15m trend") is judged on expanding-window folds. It must improve results
  in-sample in most folds *and* the pooled out-of-sample improvement must
  have a 95 % interval above zero. Otherwise it is not recommended.
* ``drift``: compares the most recent N trades of a setup with its earlier
  trades; a clearly negative difference flags that it may have stopped
  working.
"""

from __future__ import annotations

import statistics
from collections.abc import Callable
from typing import Any

from ..journal.stats import bootstrap_ci, bootstrap_diff_ci, outcome

Filter = Callable[[dict[str, Any]], bool]


def candidate_filters() -> dict[str, tuple[str, Filter]]:
    def with_tf(tf: str) -> Filter:
        return lambda t: (t.get("context") or {}).get(f"with{tf}") == "with"

    def session(s: str) -> Filter:
        return lambda t: t.get("session") == s

    return {
        "with15m": ("Ta bare handler med 15m-trenden", with_tf("15m")),
        "with1h": ("Ta bare handler med 1h-trenden", with_tf("1h")),
        "london": ("Handle bare i London-økten", session("London")),
        "ny": ("Handle bare i New York-økten", session("New York")),
        "overlap": ("Handle bare i London/NY-overlappen", session("London/NY")),
        "no_high_vol": (
            "Unngå handler når volatiliteten er høy",
            lambda t: ((t.get("context") or {}).get("tf", {}).get("1m") or {}).get("volatility") != "high",
        ),
    }


def walk_forward(
    trades: list[dict[str, Any]], rule: Filter, folds: int = 5, min_test: int = 5
) -> dict[str, Any]:
    ts = sorted((t for t in trades if t.get("closed")), key=lambda t: t["open_ms"])
    n = len(ts)
    if n < folds * min_test * 2:
        return {"recommended": False, "reason": f"for få handler ({n}) for walk-forward", "n": n}
    size = n // (folds + 1)
    results, oos_kept, oos_all, wins_in = [], [], [], 0
    for i in range(1, folds + 1):
        train, test = ts[: i * size], ts[i * size : (i + 1) * size]
        tr_keep = [outcome(t) for t in train if rule(t)]
        tr_all = [outcome(t) for t in train]
        in_gain = (statistics.fmean(tr_keep) - statistics.fmean(tr_all)) if tr_keep else 0.0
        te_keep = [outcome(t) for t in test if rule(t)]
        te_all = [outcome(t) for t in test]
        if in_gain > 0:
            wins_in += 1
        oos_kept += te_keep
        oos_all += te_all
        results.append(
            {
                "fold": i,
                "inSampleGain": round(in_gain, 3),
                "testKept": len(te_keep),
                "testMeanKept": round(statistics.fmean(te_keep), 3) if te_keep else None,
                "testMeanAll": round(statistics.fmean(te_all), 3),
            }
        )
    ci = bootstrap_diff_ci(oos_kept, oos_all) if len(oos_kept) >= 2 else None
    gain = (statistics.fmean(oos_kept) - statistics.fmean(oos_all)) if oos_kept else None
    rec = bool(ci and ci[0] > 0 and wins_in >= folds - 1)
    return {
        "recommended": rec,
        "n": n,
        "folds": results,
        "foldsImprovedInSample": wins_in,
        "oosGain": None if gain is None else round(gain, 3),
        "oosCi": None if ci is None else [round(ci[0], 3), round(ci[1], 3)],
        "reason": "bestått walk-forward" if rec else "forbedringen holdt ikke utenfor utvalget",
    }


def evaluate_candidates(trades: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out = []
    for key, (title, rule) in candidate_filters().items():
        res = walk_forward(trades, rule)
        out.append({"id": key, "title": title, **res})
    out.sort(key=lambda r: (not r["recommended"], -(r.get("oosGain") or -99)))
    return out


def drift(trades: list[dict[str, Any]], recent: int = 20, min_before: int = 20) -> list[dict[str, Any]]:
    ts = sorted((t for t in trades if t.get("closed")), key=lambda t: t["open_ms"])
    groups: dict[str, list[dict[str, Any]]] = {"(alle handler)": ts}
    for t in ts:
        if t.get("setup"):
            groups.setdefault(t["setup"], []).append(t)
    out = []
    for name, g in groups.items():
        if len(g) < recent + min_before:
            continue
        before = [outcome(t) for t in g[:-recent]]
        last = [outcome(t) for t in g[-recent:]]
        ci = bootstrap_diff_ci(last, before)
        if ci is None:
            continue
        status = "worse" if ci[1] < 0 else "better" if ci[0] > 0 else "stable"
        out.append(
            {
                "group": name,
                "status": status,
                "recentMean": round(statistics.fmean(last), 3),
                "beforeMean": round(statistics.fmean(before), 3),
                "ci": [round(ci[0], 3), round(ci[1], 3)],
                "recentCi": bootstrap_ci(last),
                "n": len(g),
            }
        )
    return out
