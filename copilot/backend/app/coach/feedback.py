"""Immediate, deterministic feedback on a closed trade."""

from __future__ import annotations

from typing import Any

from ..journal.stats import outcome


def _n(v: float, d: int = 2) -> str:
    return f"{v:.{d}f}".replace(".", ",")


def match_ai(
    trade: dict[str, Any], comments: list[dict[str, Any]], window_ms: int = 15 * 60_000
) -> dict[str, Any]:
    """Relate a trade to the latest AI comment in the window before entry.

    Purely descriptive: following a suggestion is recorded, never assumed to
    have caused the result.
    """
    before = [c for c in comments if 0 <= trade["open_ms"] - c["ts_ms"] <= window_ms]
    if not before:
        return {"status": "none"}
    c = max(before, key=lambda c: c["ts_ms"])
    setup = c.get("setup")
    if not setup:
        return {"status": "no_setup", "commentId": c["id"], "bias": c.get("bias")}
    if setup["direction"] != trade["direction"]:
        return {"status": "contrary", "commentId": c["id"]}
    lo, hi = setup["entryLow"] - 1.0, setup["entryHigh"] + 1.0
    within = lo <= trade["entry_price"] <= hi
    return {"status": "followed" if within else "same_direction", "commentId": c["id"]}


def trade_feedback(
    t: dict[str, Any],
    insights: list[dict[str, Any]],
    revenge: bool,
    ai_link: dict[str, Any],
    balance: float | None,
    max_risk_pct: float,
    typical_minutes: float | None,
) -> dict[str, Any]:
    pts: list[dict[str, str]] = []

    def add(tone: str, text: str) -> None:
        pts.append({"tone": tone, "text": text})

    r = t.get("r_multiple")
    res = f"{'+' if t['net'] >= 0 else ''}{_n(t['net'])}"
    head = f"{'Gevinst' if t['net'] > 0 else 'Tap' if t['net'] < 0 else 'Null'}: {res}"
    if r is not None:
        head += f" ({'+' if r >= 0 else ''}{_n(r)} R)"

    if not t.get("sl"):
        add("bad", "Handelen hadde ingen stop-loss ved inngang.")
    elif t.get("risk_money") and balance:
        pct = 100 * t["risk_money"] / balance
        if pct > max_risk_pct:
            add(
                "bad", f"Risikoen var {_n(pct, 1)} % av kontoen – over din grense på {_n(max_risk_pct, 1)} %."
            )
        else:
            add("good", f"Risikoen var innenfor regelen din ({_n(pct, 1)} % av kontoen).")

    ctx = t.get("context") or {}
    w15 = ctx.get("with15m")
    if w15 == "with":
        add("good", "Inngangen var i retning av 15m-trenden.")
    elif w15 == "against":
        add("warn", "Inngangen var mot 15m-trenden.")
    if ctx.get("spreadState") == "high":
        add("warn", "Spreaden var høy da du gikk inn.")

    reason = t.get("exit_reason")
    if reason == "tp":
        add("good", "Take-profit ble truffet som planlagt.")
    elif reason == "sl":
        add("neutral", "Stop-loss ble truffet – tapet var begrenset som planlagt.")
    elif reason == "manual" and t["net"] > 0 and t.get("tp"):
        dist_tp = abs(t["tp"] - t["entry_price"])
        got = abs((t.get("exit_price") or t["entry_price"]) - t["entry_price"])
        if dist_tp > 0 and got < 0.8 * dist_tp:
            add(
                "warn",
                f"Du lukket før take-profit og tok {_n(100 * got / dist_tp, 0)} % av planlagt bevegelse.",
            )
    if revenge:
        add("warn", "Handelen ble åpnet under 5 minutter etter et tap.")
    dur = ((t.get("close_ms") or t["open_ms"]) - t["open_ms"]) / 60000
    if typical_minutes and t["net"] < 0 and dur > 2 * typical_minutes:
        add(
            "warn", f"Taperen ble holdt i {_n(dur, 0)} min – mer enn dobbelt så lenge som din typiske handel."
        )

    st = ai_link.get("status")
    if st == "followed":
        add("neutral", "Handelen fulgte AI-forslaget som var aktivt da du gikk inn.")
    elif st == "contrary":
        add("neutral", "Handelen gikk mot retningen i siste AI-forslag.")

    # Personal, statistically supported patterns that apply to this trade.
    for ins in insights:
        key, diff = ins.get("id", ""), ins.get("diff")
        if diff is None:
            continue
        if key == "with:15m" and diff > 0 and w15 == "against":
            add("warn", "Historisk går det dårligere for deg mot 15m-trenden (se Coach).")
        elif key.startswith("session:") and diff < 0 and key.split(":", 1)[1] == t.get("session"):
            add("warn", f"Historisk er {t['session']}-økten svakere for deg (se Coach).")
        elif key == "revenge" and diff < 0 and revenge:
            add("warn", "Historisk går handler rett etter et tap dårligere for deg (se Coach).")
    return {"headline": head, "points": pts, "outcome": outcome(t), "aiLink": ai_link}
