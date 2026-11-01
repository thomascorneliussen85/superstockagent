"""Turns raw MT5 deals into round-trip trades (pure, deterministic)."""

from __future__ import annotations

from collections import defaultdict
from typing import Any

from ..sessions import session_of

DEAL_BUY, DEAL_SELL = 0, 1
ENTRY_IN, ENTRY_OUT, ENTRY_INOUT, ENTRY_OUT_BY = 0, 1, 2, 3
REASON_SL, REASON_TP, REASON_SO = 4, 5, 6


def _vwap(deals: list[dict[str, Any]]) -> float | None:
    vol = sum(d["volume"] for d in deals)
    return sum(d["price"] * d["volume"] for d in deals) / vol if vol > 0 else None


def money_per_price_unit(spec: dict[str, Any] | None, volume: float) -> float | None:
    if not spec:
        return None
    size, value = spec.get("tickSize") or 0, (spec.get("tickValueLoss") or spec.get("tickValue") or 0)
    return value / size * volume if size > 0 and value > 0 else None


def build_trades(
    deals: list[dict[str, Any]],
    levels: dict[int, dict[str, Any]],
    specs: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    by_pos: dict[int, list[dict[str, Any]]] = defaultdict(list)
    for d in deals:
        if d["type"] in (DEAL_BUY, DEAL_SELL) and d["position_id"]:
            by_pos[d["position_id"]].append(d)

    trades = []
    for pos, ds in by_pos.items():
        ds.sort(key=lambda d: (d["time_ms"], d["ticket"]))
        entries = [d for d in ds if d["entry"] == ENTRY_IN]
        exits = [d for d in ds if d["entry"] in (ENTRY_OUT, ENTRY_OUT_BY, ENTRY_INOUT)]
        if not entries:
            continue  # history window started mid-trade; skip incomplete position
        direction = "long" if entries[0]["type"] == DEAL_BUY else "short"
        vol_in = sum(d["volume"] for d in entries)
        vol_out = sum(d["volume"] for d in exits)
        entry_price = _vwap(entries) or entries[0]["price"]
        exit_price = _vwap(exits)
        closed = vol_out + 1e-9 >= vol_in
        gross = sum(d["profit"] for d in ds)
        commission = sum(d["commission"] for d in ds)
        swap = sum(d["swap"] for d in ds)
        fee = sum(d["fee"] for d in ds)
        net = gross + commission + swap + fee
        lv = levels.get(pos) or {}
        sl, tp = lv.get("sl"), lv.get("tp")
        risk_money = None
        per_unit = money_per_price_unit(specs.get(entries[0]["symbol"]), vol_in)
        if sl and per_unit:
            dist = (entry_price - sl) if direction == "long" else (sl - entry_price)
            if dist > 0:
                risk_money = dist * per_unit
        reason = None
        if exits:
            r = exits[-1].get("reason")
            reason = {REASON_SL: "sl", REASON_TP: "tp", REASON_SO: "stopout"}.get(r, "manual")
        trades.append(
            {
                "position_id": pos,
                "symbol": entries[0]["symbol"],
                "direction": direction,
                "open_ms": entries[0]["time_ms"],
                "close_ms": exits[-1]["time_ms"] if closed and exits else None,
                "volume": round(vol_in, 4),
                "entry_price": entry_price,
                "exit_price": exit_price,
                "sl": sl,
                "tp": tp,
                "gross": round(gross, 2),
                "commission": round(commission, 2),
                "swap": round(swap, 2),
                "fee": round(fee, 2),
                "net": round(net, 2),
                "risk_money": None if risk_money is None else round(risk_money, 2),
                "r_multiple": None if not risk_money or not closed else round(net / risk_money, 3),
                "exit_reason": reason,
                "closed": int(closed),
                "session": session_of(entries[0]["time_ms"]),
                "deals": len(ds),
            }
        )
    trades.sort(key=lambda t: t["open_ms"])
    return trades
