"""Simulated broker for replay: market orders with attached SL/TP.

Fill rules (bid-based charts, like MT5):
* BUY fills at the ask, SELL at the bid (+ optional slippage against you).
* A long is closed at the bid: SL when bid <= SL (filled at the bid, so gaps
  can be worse than SL), TP when bid >= TP (filled at TP, a limit order).
* A short is closed at the ask: SL when ask >= SL, TP when ask <= TP.
* Commission is charged per lot round turn.
Profit = price difference x contract size x lots (in the quote currency, USD).
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

from ..market.models import Tick


@dataclass
class SimPosition:
    id: int
    side: str  # "buy" | "sell"
    volume: float
    entry: float
    sl: float | None
    tp: float | None
    open_ms: int
    risk_money: float | None
    mfe: float = 0.0  # best unrealised P/L seen
    mae: float = 0.0  # worst unrealised P/L seen
    profit: float = 0.0

    def to_wire(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class SimTrade:
    id: int
    side: str
    volume: float
    entry: float
    exit: float
    sl: float | None
    tp: float | None
    open_ms: int
    close_ms: int
    gross: float
    commission: float
    net: float
    risk_money: float | None
    r_multiple: float | None
    exit_reason: str
    mfe: float
    mae: float

    def to_wire(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class SimBroker:
    contract_size: float = 100.0
    commission_per_lot: float = 7.0
    slippage: float = 0.0
    balance: float = 10_000.0
    positions: dict[int, SimPosition] = field(default_factory=dict)
    trades: list[SimTrade] = field(default_factory=list)
    _next_id: int = 1
    last: Tick | None = None

    def _pnl(self, p: SimPosition, price: float) -> float:
        diff = (price - p.entry) if p.side == "buy" else (p.entry - price)
        return diff * self.contract_size * p.volume

    def market_order(
        self, side: str, volume: float, sl_distance: float | None, tp_distance: float | None
    ) -> SimPosition:
        if self.last is None:
            raise ValueError("ingen pris ennå")
        if side not in ("buy", "sell") or volume <= 0:
            raise ValueError("ugyldig ordre")
        t = self.last
        entry = (t.ask + self.slippage) if side == "buy" else (t.bid - self.slippage)
        sl = tp = None
        if sl_distance:
            sl = entry - sl_distance if side == "buy" else entry + sl_distance
        if tp_distance:
            tp = entry + tp_distance if side == "buy" else entry - tp_distance
        risk = None
        if sl is not None:
            risk = abs(entry - sl) * self.contract_size * volume + self.commission_per_lot * volume
        p = SimPosition(
            self._next_id,
            side,
            volume,
            round(entry, 2),
            sl and round(sl, 2),
            tp and round(tp, 2),
            t.time_ms,
            risk and round(risk, 2),
        )
        self._next_id += 1
        self.positions[p.id] = p
        return p

    def close(self, pid: int, reason: str = "manual", price: float | None = None) -> SimTrade | None:
        p = self.positions.pop(pid, None)
        if p is None or self.last is None:
            return None
        t = self.last
        exit_price = price if price is not None else (t.bid if p.side == "buy" else t.ask)
        gross = self._pnl(p, exit_price)
        commission = -self.commission_per_lot * p.volume
        net = gross + commission
        self.balance += net
        trade = SimTrade(
            p.id,
            p.side,
            p.volume,
            p.entry,
            round(exit_price, 2),
            p.sl,
            p.tp,
            p.open_ms,
            t.time_ms,
            round(gross, 2),
            round(commission, 2),
            round(net, 2),
            p.risk_money,
            None if not p.risk_money else round(net / p.risk_money, 3),
            reason,
            round(p.mfe, 2),
            round(p.mae, 2),
        )
        self.trades.append(trade)
        return trade

    def close_all(self) -> list[SimTrade]:
        return [tr for pid in list(self.positions) if (tr := self.close(pid)) is not None]

    def on_tick(self, t: Tick) -> list[SimTrade]:
        """Update prices; returns trades closed by SL/TP on this tick."""
        self.last = t
        closed: list[SimTrade] = []
        for pid, p in list(self.positions.items()):
            if p.side == "buy":
                if p.sl is not None and t.bid <= p.sl:
                    closed.append(self.close(pid, "sl", t.bid))
                    continue
                if p.tp is not None and t.bid >= p.tp:
                    closed.append(self.close(pid, "tp", p.tp))
                    continue
                p.profit = self._pnl(p, t.bid)
            else:
                if p.sl is not None and t.ask >= p.sl:
                    closed.append(self.close(pid, "sl", t.ask))
                    continue
                if p.tp is not None and t.ask <= p.tp:
                    closed.append(self.close(pid, "tp", p.tp))
                    continue
                p.profit = self._pnl(p, t.ask)
            p.mfe, p.mae = max(p.mfe, p.profit), min(p.mae, p.profit)
        return [c for c in closed if c is not None]

    @property
    def equity(self) -> float:
        return self.balance + sum(p.profit for p in self.positions.values())

    def state(self) -> dict[str, Any]:
        return {
            "balance": round(self.balance, 2),
            "equity": round(self.equity, 2),
            "positions": [p.to_wire() for p in self.positions.values()],
            "trades": [t.to_wire() for t in self.trades[-50:]],
            "commissionPerLot": self.commission_per_lot,
            "contractSize": self.contract_size,
        }
