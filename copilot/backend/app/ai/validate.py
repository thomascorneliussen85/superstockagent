"""Deterministic sanity checks on the model's proposed setup.

The language model may describe a setup, but the numbers are checked here:
levels on the correct side, entry close to the market, and the risk/reward
computed by code (including the spread), never taken from the model.
"""

from __future__ import annotations

from typing import Any


def risk_reward(
    direction: str, entry: float, invalidation: float, target: float, spread: float
) -> float | None:
    """R/R after costs. Buying pays the spread on entry, selling pays it on exit,
    so in both cases the spread reduces the reward and adds to the risk."""
    risk = abs(entry - invalidation) + spread
    reward = abs(target - entry) - spread
    if risk <= 0:
        return None
    return reward / risk


def validate_setup(
    setup: dict[str, Any], bid: float | None, ask: float | None, atr_1m: float | None, digits: int = 2
) -> tuple[dict[str, Any] | None, str | None]:
    """Returns (checked setup, None) or (None, reason it was rejected/absent)."""
    direction = setup.get("direction")
    if direction not in ("long", "short"):
        return None, None
    if bid is None or ask is None:
        return None, "ingen pris å vurdere oppsettet mot"
    lo, hi = sorted((float(setup["entry_low"]), float(setup["entry_high"])))
    inv, tgt = float(setup["invalidation"]), float(setup["target"])
    spread = ask - bid
    entry = (lo + hi) / 2

    if direction == "long" and not (inv < lo and tgt > hi):
        return None, "nivåene stemmer ikke for long (invalidering må ligge under, mål over)"
    if direction == "short" and not (inv > hi and tgt < lo):
        return None, "nivåene stemmer ikke for short (invalidering må ligge over, mål under)"

    max_dist = max(3 * (atr_1m or 0), 2.0)
    if abs(entry - bid) > max_dist:
        return None, "inngangssonen ligger for langt fra dagens pris"

    rr = risk_reward(direction, entry, inv, tgt, spread)
    if rr is None or rr <= 0:
        return None, "målet dekker ikke spreaden"

    risk_usd_per_oz = abs(entry - inv) + spread
    checked = {
        "direction": direction,
        "kind": setup.get("kind", "none"),
        "entryLow": round(lo, digits),
        "entryHigh": round(hi, digits),
        "invalidation": round(inv, digits),
        "target": round(tgt, digits),
        "rr": round(rr, 2),
        "riskPerOz": round(risk_usd_per_oz, digits),
        "spreadAtCheck": round(spread, digits),
        "supporting": [str(x) for x in setup.get("supporting", [])][:6],
        "conflicting": [str(x) for x in setup.get("conflicting", [])][:6],
    }
    return checked, None
