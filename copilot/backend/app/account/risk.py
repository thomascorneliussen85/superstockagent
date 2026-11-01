"""Deterministic risk view of the MT5 account and its open positions.

Pure functions: raw account/position data in, enriched figures and alerts
out. Money at risk is always computed from the instrument's own contract
specification (tick size and tick value in the account currency, from MT5),
never from assumptions about lot sizes.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class RiskRules:
    max_per_trade_pct: float = 1.0
    daily_loss_limit_pct: float = 3.0
    near_sl_fraction: float = 0.25
    min_margin_level_pct: float = 200.0


def money_per_price_unit(spec: dict[str, Any], volume: float, loss: bool = True) -> float | None:
    """Account-currency value of a 1.0 price move for ``volume`` lots."""
    tick_size = spec.get("tickSize") or 0
    tick_value = (spec.get("tickValueLoss") if loss else None) or spec.get("tickValue") or 0
    if tick_size > 0 and tick_value > 0:
        return tick_value / tick_size * volume
    return None


def nf(v: float, decimals: int = 1) -> str:
    """Norwegian number format: decimal comma."""
    return f"{v:.{decimals}f}".replace(".", ",")


def symbol_group(symbol: str) -> str:
    s = symbol.upper()
    if "XAU" in s or "GOLD" in s:
        return "gull"
    if "XAG" in s or "SILVER" in s:
        return "sølv"
    return s


def enrich_position(p: dict[str, Any], balance: float, rules: RiskRules, atr: float | None) -> dict[str, Any]:
    spec = p.get("spec", {})
    buy = p["type"] == "buy"
    open_, cur, sl, tp, vol = p["priceOpen"], p["priceCurrent"], p["sl"], p["tp"], p["volume"]
    per_unit = money_per_price_unit(spec, vol)
    out = {k: v for k, v in p.items() if k != "spec"}
    out["oz"] = round(vol * (spec.get("contractSize") or 0), 4)
    out["digits"] = spec.get("digits", 2)

    risk_money = None  # money lost if SL is hit, measured from the entry price
    locked = None  # profit locked in when SL is beyond entry
    to_sl_money = None  # additional loss from current price to SL
    sl_progress = None  # 1 = at entry, 0 = at SL
    dist_sl = None
    if sl > 0 and per_unit:
        signed = (open_ - sl) if buy else (sl - open_)
        if signed > 0:
            risk_money = signed * per_unit
        else:
            locked = -signed * per_unit
        dist_sl = (cur - sl) if buy else (sl - cur)
        to_sl_money = max(0.0, dist_sl) * per_unit
        if signed > 0:
            sl_progress = max(0.0, min(1.0, dist_sl / signed)) if signed else None
    out.update(
        {
            "riskMoney": None if risk_money is None else round(risk_money, 2),
            "riskPct": None if risk_money is None or balance <= 0 else round(100 * risk_money / balance, 2),
            "lockedMoney": None if locked is None else round(locked, 2),
            "toSlMoney": None if to_sl_money is None else round(to_sl_money, 2),
            "distToSl": None if dist_sl is None else round(dist_sl, out["digits"]),
            "distToSlAtr": None if dist_sl is None or not atr else round(dist_sl / atr, 2),
            "slProgress": None if sl_progress is None else round(sl_progress, 3),
            "distToTp": None if tp <= 0 else round((tp - cur) if buy else (cur - tp), out["digits"]),
            "rMultiple": None if not risk_money else round((p["profit"] + p.get("swap", 0)) / risk_money, 2),
        }
    )
    return out


def position_alerts(p: dict[str, Any], rules: RiskRules, atr: float | None) -> list[dict[str, Any]]:
    t = p["ticket"]
    side = "long" if p["type"] == "buy" else "short"
    name = f"{p['symbol']} {side} {nf(p['volume'], 2)} lot"
    out: list[dict[str, Any]] = []
    if p["sl"] <= 0:
        out.append(alert(f"nosl:{t}", "critical", f"{name} har ingen stop-loss.", t, "risk"))
    if p.get("riskPct") is not None and p["riskPct"] > rules.max_per_trade_pct:
        out.append(
            alert(
                f"risk:{t}",
                "warn",
                f"{name} risikerer {nf(p['riskPct'])} % av kontoen"
                f" (din grense er {nf(rules.max_per_trade_pct)} %).",
                t,
                "risk",
            )
        )
    near = False
    if p.get("slProgress") is not None and p["slProgress"] <= rules.near_sl_fraction:
        near = True
    if p.get("distToSlAtr") is not None and p["sl"] > 0 and 0 <= p["distToSlAtr"] <= 0.5:
        near = True
    if near:
        out.append(
            alert(
                f"nearsl:{t}",
                "warn",
                f"{name} nærmer seg stop-loss ({nf(p['sl'], p.get('digits', 2))}).",
                t,
                "sl",
            )
        )
    return out


def alert(key: str, level: str, text: str, ticket: int | None = None, kind: str = "risk") -> dict[str, Any]:
    return {"key": key, "level": level, "text": text, "ticket": ticket, "kind": kind}


def build_account_view(
    raw: dict[str, Any],
    rules: RiskRules,
    atr_by_symbol: dict[str, float | None] | None = None,
    spread_high_symbols: set[str] | None = None,
) -> dict[str, Any]:
    acc = raw["account"]
    balance = acc["balance"]
    atr_by_symbol = atr_by_symbol or {}
    positions = [
        enrich_position(p, balance, rules, atr_by_symbol.get(p["symbol"])) for p in raw.get("positions", [])
    ]
    alerts: list[dict[str, Any]] = []
    for p in positions:
        alerts += position_alerts(p, rules, atr_by_symbol.get(p["symbol"]))

    # Correlated exposure: several positions in the same direction on the same underlying.
    groups: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for p in positions:
        groups.setdefault((symbol_group(p["symbol"]), p["type"]), []).append(p)
    for (grp, typ), ps in groups.items():
        if len(ps) >= 2:
            total = sum(p["riskMoney"] or 0 for p in ps)
            side = "long" if typ == "buy" else "short"
            text = f"Du har {len(ps)} {side}-posisjoner i {grp} samtidig – de beveger seg sammen"
            text += f" (samlet risiko {nf(total, 0)} {acc['currency']})." if total else "."
            alerts.append(alert(f"corr:{grp}:{typ}:{len(ps)}", "warn", text, None, "risk"))

    for sym in sorted(spread_high_symbols or set()):
        if any(p["symbol"] == sym or symbol_group(p["symbol"]) == symbol_group(sym) for p in positions):
            alerts.append(
                alert(
                    f"spread:{sym}",
                    "warn",
                    "Spreaden har økt kraftig mens du har en åpen posisjon.",
                    None,
                    "spread",
                )
            )

    # Daily loss limit, measured against the balance at the start of the day.
    realized = raw.get("dayRealized", 0.0)
    floating = sum(p["profit"] + p.get("swap", 0) for p in positions)
    open_risk = sum(p["riskMoney"] or 0 for p in positions)
    no_sl = any(p["sl"] <= 0 for p in positions)
    start_balance = balance - realized
    limit = start_balance * rules.daily_loss_limit_pct / 100 if start_balance > 0 else 0.0
    day_result = realized + floating
    worst_case_day = realized - open_risk  # if every open SL is hit (ignoring current floating)
    if limit > 0:
        if -day_result >= limit:
            alerts.append(
                alert(
                    "daily:reached",
                    "critical",
                    f"Du har nådd din daglige tapsgrense ({nf(rules.daily_loss_limit_pct)} %).",
                    None,
                    "daily",
                )
            )
        elif -day_result >= 0.8 * limit:
            alerts.append(alert("daily:near", "warn", "Du er nær din daglige tapsgrense.", None, "daily"))
        elif positions and (-worst_case_day > limit or no_sl):
            alerts.append(
                alert(
                    "daily:open",
                    "warn",
                    "Åpen risiko kan ta deg over den daglige tapsgrensen hvis stop-loss treffes.",
                    None,
                    "daily",
                )
            )
    ml = acc.get("marginLevel") or 0
    if positions and 0 < ml < rules.min_margin_level_pct:
        alerts.append(alert("margin:low", "critical", f"Lavt marginnivå: {nf(ml, 0)} %.", None, "risk"))

    order = {"critical": 0, "warn": 1, "info": 2}
    alerts.sort(key=lambda a: order[a["level"]])
    return {
        "available": True,
        "account": acc,
        "positions": positions,
        "pendingOrders": raw.get("pendingOrders", 0),
        "day": {
            "realized": round(realized, 2),
            "floating": round(floating, 2),
            "result": round(day_result, 2),
            "startBalance": round(start_balance, 2),
            "limitMoney": round(limit, 2),
            "limitPct": rules.daily_loss_limit_pct,
            "usedPct": None if limit <= 0 else round(max(0.0, -day_result) / limit * 100, 1),
            "openRisk": round(open_risk, 2),
            "anyWithoutSl": no_sl,
            "closedTrades": raw.get("dayClosedDeals", 0),
        },
        "rules": {
            "maxPerTradePct": rules.max_per_trade_pct,
            "dailyLossLimitPct": rules.daily_loss_limit_pct,
        },
        "alerts": alerts,
    }
