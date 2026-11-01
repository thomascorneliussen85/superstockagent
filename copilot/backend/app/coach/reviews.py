"""Daily and weekly reviews: deterministic facts first, optional AI narrative on top."""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

from ..journal.stats import compute_stats, group_metrics
from ..sessions import OSLO
from .insights import revenge_flags

REVIEW_SYSTEM = """\
Du er en erfaren, ærlig tradingcoach for en person som scalper gull (XAUUSD) manuelt. Du får \
fakta om en handelsperiode beregnet av kode: statistikk, regelbrudd, statistisk underbygde mønstre \
(med utvalgsstørrelse og konfidensintervall) og hvordan AI-forslagene traff. Skriv på norsk (bokmål), \
kort og konkret. Bruk bare tallene du får; ikke finn på noe. Mønstre merket «foreløpig» skal omtales \
forsiktig. Ikke lov fortjeneste, og ikke gi råd om å endre risikogrenser – de bestemmer traderen selv. \
Gi 1-3 konkrete, gjennomførbare forbedringer knyttet til fakta."""

REVIEW_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "summary": {"type": "string"},
        "went_well": {"type": "array", "items": {"type": "string"}},
        "improve": {"type": "array", "items": {"type": "string"}},
        "focus_next": {"type": "string"},
    },
    "required": ["summary", "went_well", "improve", "focus_next"],
    "additionalProperties": False,
}


def period_bounds(period: str, now: datetime) -> tuple[int, int, str]:
    local = now.astimezone(OSLO)
    day0 = local.replace(hour=0, minute=0, second=0, microsecond=0)
    if period == "day":
        start, end = day0, day0 + timedelta(days=1)
        label = start.strftime("%d.%m.%Y")
    else:
        start = day0 - timedelta(days=local.weekday())
        end = start + timedelta(days=7)
        label = f"uke {start.isocalendar().week} ({start.strftime('%d.%m')}–{(end - timedelta(days=1)).strftime('%d.%m')})"
    return int(start.timestamp() * 1000), int(end.timestamp() * 1000), label


def adherence(
    trades: list[dict[str, Any]], all_trades: list[dict[str, Any]], max_risk_pct: float, balance: float | None
) -> dict[str, Any]:
    n = len(trades)
    if n == 0:
        return {"n": 0}
    rev = revenge_flags(all_trades)
    with_sl = sum(1 for t in trades if t.get("sl"))
    over = None
    if balance:
        over = sum(
            1 for t in trades if t.get("risk_money") and 100 * t["risk_money"] / balance > max_risk_pct
        )
    against = sum(1 for t in trades if (t.get("context") or {}).get("with15m") == "against")
    return {
        "n": n,
        "withSl": with_sl,
        "withSlPct": round(100 * with_sl / n, 1),
        "overRiskRule": over,
        "against15m": against,
        "revenge": sum(1 for t in trades if rev.get(t["position_id"])),
        "earlyExits": sum(
            1 for t in trades if t.get("exit_reason") == "manual" and t["net"] > 0 and t.get("tp")
        ),
    }


def build_review(
    period: str,
    label: str,
    trades: list[dict[str, Any]],
    all_trades: list[dict[str, Any]],
    insights: list[dict[str, Any]],
    ai_summary: dict[str, Any] | None,
    max_risk_pct: float,
    balance: float | None,
) -> dict[str, Any]:
    stats = compute_stats(trades)
    adh = adherence(trades, all_trades, max_risk_pct, balance)
    closed = [t for t in trades if t.get("closed")]
    best = max(closed, key=lambda t: t["net"], default=None)
    worst = min(closed, key=lambda t: t["net"], default=None)
    suggestions: list[str] = []
    if adh.get("n"):
        if adh["withSl"] < adh["n"]:
            suggestions.append(
                f"{adh['n'] - adh['withSl']} handler manglet stop-loss ved inngang – sett SL før du går inn."
            )
        if adh.get("overRiskRule"):
            suggestions.append(
                f"{adh['overRiskRule']} handler risikerte mer enn {max_risk_pct:g} % av kontoen."
            )
        if adh["revenge"]:
            suggestions.append(
                f"{adh['revenge']} handler ble åpnet under 5 minutter etter et tap – ta en pause etter tap."
            )
        if adh["against15m"] and any(i["id"] == "with:15m" and i["diff"] > 0 for i in insights):
            suggestions.append(
                f"{adh['against15m']} handler gikk mot 15m-trenden, som historisk er svakere for deg."
            )
    for ins in insights[:3]:
        if ins.get("kind") in ("weakness", "habit"):
            suggestions.append(f"Mønster ({ins['strength']}): {ins['title']}")
    return {
        "period": period,
        "label": label,
        "stats": stats.get("summary"),
        "bySession": stats.get("bySession", []),
        "byDirection": stats.get("byDirection", []),
        "adherence": adh,
        "best": None
        if not best
        else {"position_id": best["position_id"], "net": best["net"], "r": best.get("r_multiple")},
        "worst": None
        if not worst
        else {"position_id": worst["position_id"], "net": worst["net"], "r": worst.get("r_multiple")},
        "patterns": [
            {k: i.get(k) for k in ("id", "kind", "title", "detail", "strength")} for i in insights[:6]
        ],
        "ai": None if not ai_summary else ai_summary.get("all"),
        "suggestions": suggestions[:6],
        "compareAll": group_metrics([t for t in all_trades if t.get("closed")]),
    }


def review_prompt(review: dict[str, Any]) -> str:
    import json

    facts = {
        k: review[k]
        for k in (
            "label",
            "stats",
            "adherence",
            "best",
            "worst",
            "patterns",
            "ai",
            "suggestions",
            "compareAll",
            "bySession",
            "byDirection",
        )
    }
    return "Fakta for perioden (JSON):\n" + json.dumps(facts, ensure_ascii=False, separators=(",", ":"))
