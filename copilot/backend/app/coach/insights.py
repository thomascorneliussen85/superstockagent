"""Statistically supported patterns in the trader's own history.

Every claim compares a group of trades with the rest, using the per-trade
outcome (R multiple when known, else money). A pattern is only reported when
* both groups have at least ``min_n`` trades, and
* the 95 % bootstrap confidence interval of the difference excludes zero.
Patterns backed by fewer than 50 trades in the smaller group are labelled
"foreløpig" (preliminary). Many splits are tested, so a few false positives
remain possible; the label and the interval are always shown.
"""

from __future__ import annotations

import statistics
from collections.abc import Callable
from typing import Any

from ..journal.stats import bootstrap_diff_ci, wilson
from ..sessions import SESSIONS, oslo

SOLID_N = 50


def _fmt(v: float, unit: str) -> str:
    s = f"{v:+.2f}".replace(".", ",") if unit == "R" else f"{v:+.0f}"
    return f"{s} R" if unit == "R" else f"{s}"


def _n(v: float, d: int = 1) -> str:
    return f"{v:.{d}f}".replace(".", ",")


def _unit(trades: list[dict[str, Any]]) -> str:
    with_r = sum(1 for t in trades if t.get("r_multiple") is not None)
    return "R" if trades and with_r >= 0.8 * len(trades) else "money"


def _values(trades: list[dict[str, Any]], unit: str) -> list[float]:
    if unit == "R":
        return [t["r_multiple"] for t in trades if t.get("r_multiple") is not None]
    return [t["net"] for t in trades]


def compare(
    trades: list[dict[str, Any]],
    pred: Callable[[dict[str, Any]], bool | None],
    label_a: str,
    label_b: str,
    key: str,
    min_n: int,
) -> dict[str, Any] | None:
    unit = _unit(trades)
    a = [t for t in trades if pred(t) is True]
    b = [t for t in trades if pred(t) is False]
    va, vb = _values(a, unit), _values(b, unit)
    if len(va) < min_n or len(vb) < min_n:
        return None
    # Cheap screen first (Welch z); only plausible differences get the costly bootstrap.
    se = (statistics.pvariance(va) / len(va) + statistics.pvariance(vb) / len(vb)) ** 0.5
    if se == 0 or abs(statistics.fmean(va) - statistics.fmean(vb)) / se < 1.6:
        return None
    ci = bootstrap_diff_ci(va, vb, iters=1000)
    if ci is None or (ci[0] <= 0 <= ci[1]):
        return None
    ma, mb = statistics.fmean(va), statistics.fmean(vb)
    better = ma > mb
    n_small = min(len(va), len(vb))
    title = (
        f"Du gjør det bedre {label_a} enn {label_b}."
        if better
        else f"Du gjør det svakere {label_a} enn {label_b}."
    )
    return {
        "id": key,
        "kind": "strength" if better else "weakness",
        "title": title,
        "detail": (
            f"Snitt per handel {label_a}: {_fmt(ma, unit)} (n={len(va)}), {label_b}: {_fmt(mb, unit)} "
            f"(n={len(vb)}). 95 %-intervall for forskjellen: {_fmt(ci[0], unit)} til {_fmt(ci[1], unit)}."
        ),
        "unit": unit,
        "a": {"label": label_a, "n": len(va), "mean": round(ma, 3)},
        "b": {"label": label_b, "n": len(vb), "mean": round(mb, 3)},
        "diff": round(ma - mb, 3),
        "ci": [round(ci[0], 3), round(ci[1], 3)],
        "strength": "solid" if n_small >= SOLID_N else "foreløpig",
    }


def _with(tf: str):
    def f(t: dict[str, Any]) -> bool | None:
        v = (t.get("context") or {}).get(f"with{tf}")
        return None if v in (None, "neutral") else v == "with"

    return f


def revenge_flags(trades: list[dict[str, Any]], window_ms: int = 5 * 60_000) -> dict[int, bool]:
    """True if the trade was opened within ``window_ms`` after a losing trade closed."""
    out: dict[int, bool] = {}
    closed = sorted((t for t in trades if t.get("close_ms")), key=lambda t: t["close_ms"])
    for t in trades:
        prev = [p for p in closed if p["close_ms"] <= t["open_ms"] and p["position_id"] != t["position_id"]]
        out[t["position_id"]] = (
            bool(prev) and prev[-1]["net"] < 0 and t["open_ms"] - prev[-1]["close_ms"] <= window_ms
        )
    return out


def find_insights(trades: list[dict[str, Any]], min_n: int = 20) -> list[dict[str, Any]]:
    trades = [t for t in trades if t.get("closed")]
    found: list[dict[str, Any]] = []

    def add(x: dict[str, Any] | None) -> None:
        if x:
            found.append(x)

    for s in SESSIONS:
        add(
            compare(
                trades,
                lambda t, s=s: t["session"] == s,
                f"i {s}-økten",
                "i andre økter",
                f"session:{s}",
                min_n,
            )
        )
    for tf in ("15m", "1h", "5m"):
        add(compare(trades, _with(tf), f"med {tf}-trenden", f"mot {tf}-trenden", f"with:{tf}", min_n))
    add(compare(trades, lambda t: t["direction"] == "long", "på long", "på short", "dir", min_n))
    for h in range(24):
        add(
            compare(
                trades,
                lambda t, h=h: oslo(t["open_ms"]).hour == h,
                f"kl. {h:02d}-{h + 1:02d}",
                "resten av døgnet",
                f"hour:{h}",
                min_n,
            )
        )
    for d, name in enumerate(["mandag", "tirsdag", "onsdag", "torsdag", "fredag"]):
        add(
            compare(
                trades,
                lambda t, d=d: oslo(t["open_ms"]).weekday() == d,
                f"på {name}",
                "andre dager",
                f"weekday:{d}",
                min_n,
            )
        )
    add(
        compare(
            trades,
            lambda t: (
                None
                if not (t.get("context") or {}).get("tf", {}).get("1m")
                else (t["context"]["tf"]["1m"].get("volatility") == "high")
            ),
            "når volatiliteten er høy",
            "ellers",
            "volatility:high",
            min_n,
        )
    )
    setups = {t.get("setup") for t in trades if t.get("setup")}
    for s in sorted(setups):
        add(
            compare(
                trades,
                lambda t, s=s: (t.get("setup") or None) == s,
                f"med oppsettet «{s}»",
                "andre oppsett",
                f"setup:{s}",
                min_n,
            )
        )
    rev = revenge_flags(trades)
    add(
        compare(
            trades,
            lambda t: rev.get(t["position_id"]),
            "rett etter et tap (< 5 min)",
            "ellers",
            "revenge",
            min_n,
        )
    )
    vols = [t["volume"] for t in trades]
    if vols:
        med = statistics.median(vols)
        add(
            compare(
                trades,
                lambda t: t["volume"] > 1.5 * med,
                "med større posisjoner enn vanlig",
                "med normal størrelse",
                "size:large",
                min_n,
            )
        )
    add(
        compare(
            trades,
            lambda t: None if t.get("sl") is None and t.get("r_multiple") is None else bool(t.get("sl")),
            "med stop-loss",
            "uten stop-loss",
            "sl",
            min_n,
        )
    )
    found.sort(key=lambda x: (x["strength"] != "solid", -abs(x["diff"])))
    return found + habit_insights(trades, min_n)


def habit_insights(trades: list[dict[str, Any]], min_n: int) -> list[dict[str, Any]]:
    """Behavioural frequencies (not comparisons) with Wilson intervals."""
    out = []
    winners_with_tp = [t for t in trades if t["net"] > 0 and t.get("tp")]
    if len(winners_with_tp) >= min_n:
        early = [t for t in winners_with_tp if t.get("exit_reason") == "manual"]
        p = len(early) / len(winners_with_tp)
        lo, hi = wilson(len(early), len(winners_with_tp))
        if lo >= 0.4:
            out.append(
                {
                    "id": "habit:early-exit",
                    "kind": "habit",
                    "title": "Du lukker ofte vinnende handler før planlagt take-profit.",
                    "detail": f"{len(early)} av {len(winners_with_tp)} vinnere med TP ble lukket manuelt før TP "
                    f"({p:.0%}, 95 %-intervall {lo:.0%}–{hi:.0%}).",
                    "n": len(winners_with_tp),
                    "rate": round(p, 3),
                    "ci": [round(lo, 3), round(hi, 3)],
                    "strength": "solid" if len(winners_with_tp) >= SOLID_N else "foreløpig",
                }
            )
    wins = [(t["close_ms"] - t["open_ms"]) / 60000 for t in trades if t["net"] > 0 and t.get("close_ms")]
    losses = [(t["close_ms"] - t["open_ms"]) / 60000 for t in trades if t["net"] < 0 and t.get("close_ms")]
    if len(wins) >= min_n and len(losses) >= min_n:
        ci = bootstrap_diff_ci(losses, wins)
        if ci and ci[0] > 0:
            ratio = statistics.fmean(losses) / max(0.1, statistics.fmean(wins))
            out.append(
                {
                    "id": "habit:hold-losers",
                    "kind": "habit",
                    "title": "Du holder tapende handler lenger enn vinnende.",
                    "detail": f"Snitt {_n(statistics.fmean(losses))} min for tapere mot {_n(statistics.fmean(wins))} min "
                f"for vinnere ({_n(ratio)}×).",
                    "n": len(wins) + len(losses),
                    "ci": [round(ci[0], 2), round(ci[1], 2)],
                    "strength": "solid" if min(len(wins), len(losses)) >= SOLID_N else "foreløpig",
                }
            )
    return out
