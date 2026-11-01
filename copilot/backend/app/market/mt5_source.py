"""Read-only MetaTrader 5 market data source.

Requirements: Windows, the ``MetaTrader5`` package, and an MT5 terminal that
is running and logged in on the same PC.

Safety
------
This module only calls read functions of the MetaTrader5 API (initialize,
account/terminal/symbol info, tick and rate copies). It never calls
``order_send``/``order_check`` or anything that changes positions; a unit
test scans the code base to enforce that.

Threading
---------
The MetaTrader5 package is blocking and not thread-safe, so every call runs
on one dedicated worker thread.

Time
----
MT5 reports tick and bar times in *broker server time* encoded as epoch
values. They are converted to UTC by subtracting the broker's UTC offset,
which is detected from a live tick (rounded to 30 minutes), taken from
configuration, or loaded from the last successful detection.
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from collections.abc import AsyncIterator, Callable
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

from .models import Candle, SymbolSpec, Tick, Timeframe

log = logging.getLogger(__name__)

# Constant values from the MetaTrader5 package, used if the module lacks them (tests).
_DEFAULTS = {
    "COPY_TICKS_INFO": 1,
    "TIMEFRAME_M1": 1,
    "TIMEFRAME_M5": 5,
    "TIMEFRAME_M15": 15,
    "TIMEFRAME_H1": 16385,
    "ACCOUNT_TRADE_MODE_DEMO": 0,
    "ACCOUNT_TRADE_MODE_CONTEST": 1,
    "ACCOUNT_TRADE_MODE_REAL": 2,
    "POSITION_TYPE_BUY": 0,
    "POSITION_TYPE_SELL": 1,
    "DEAL_TYPE_BUY": 0,
    "DEAL_TYPE_SELL": 1,
    "COPY_TICKS_ALL": -1,
}

_TF_CODES = {"1m": "TIMEFRAME_M1", "5m": "TIMEFRAME_M5", "15m": "TIMEFRAME_M15", "1h": "TIMEFRAME_H1"}

HALF_HOUR_MS = 30 * 60 * 1000
OFFSET_FILE = "mt5_utc_offset.json"
TICK_BATCH = 1000


class Mt5Error(RuntimeError):
    #: Message is written for the end user and shown as-is in the panel.
    user_facing = True


class Mt5ConfigError(Mt5Error):
    """Configuration does not match the terminal/account (not fixed by retrying quickly)."""


def _c(mt5: Any, name: str) -> int:
    return getattr(mt5, name, _DEFAULTS[name])


def round_offset(server_ms: int, utc_ms: int) -> int:
    return round((server_ms - utc_ms) / HALF_HOUR_MS) * HALF_HOUR_MS


def load_mt5_module() -> Any:
    try:
        import MetaTrader5  # type: ignore[import-not-found]
    except ImportError as exc:  # pragma: no cover - depends on platform
        raise Mt5ConfigError(
            "MetaTrader5-pakken er ikke installert. Den finnes kun for Windows "
            "(pip install MetaTrader5, Python 3.10-3.14)."
        ) from exc
    return MetaTrader5


class Mt5MarketSource:
    name = "mt5"
    is_synthetic = False

    def __init__(
        self,
        expected_mode: str = "mt5",
        broker_symbol: str | None = None,
        terminal_path: str | None = None,
        utc_offset_minutes: int | None = None,
        data_dir: Path | None = None,
        poll_interval: float = 0.1,
        module_loader: Callable[[], Any] = load_mt5_module,
        wall_ms: Callable[[], int] | None = None,
    ) -> None:
        self.expected_mode = expected_mode
        self._broker_symbol_cfg = broker_symbol
        self._terminal_path = terminal_path
        self._offset_cfg_ms = None if utc_offset_minutes is None else utc_offset_minutes * 60_000
        self._data_dir = data_dir
        self._poll = poll_interval
        self._loader = module_loader
        self._wall_ms = wall_ms or (lambda: int(time.time() * 1000))
        self._ex = ThreadPoolExecutor(max_workers=1, thread_name_prefix="mt5")
        self._mt5: Any = None
        self._broker_symbol: str | None = None
        self._spec: SymbolSpec | None = None
        self.offset_ms: int = 0
        self.resolved_mode: str | None = None
        self.account: dict[str, Any] | None = None
        self.warnings: list[str] = []
        self._closed = False

    # ---- thread helpers ----------------------------------------------------
    async def _call(self, fn: Callable[..., Any], *args: Any) -> Any:
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(self._ex, lambda: fn(*args))

    def _err(self, what: str) -> Mt5Error:
        code = None
        try:
            code = self._mt5.last_error() if self._mt5 else None
        except Exception:  # noqa: BLE001
            pass
        return Mt5Error(f"{what} (MT5 last_error={code})")

    # ---- connection --------------------------------------------------------
    def _connect_sync(self) -> None:
        if self._mt5 is None:
            self._mt5 = self._loader()
        mt5 = self._mt5
        ok = mt5.initialize(path=self._terminal_path) if self._terminal_path else mt5.initialize()
        if not ok:
            raise self._err("Fikk ikke kontakt med MT5-terminalen. Er MetaTrader 5 startet og innlogget?")
        acc = mt5.account_info()
        if acc is None:
            raise self._err("MT5 er startet, men ingen konto er innlogget")
        real = acc.trade_mode == _c(mt5, "ACCOUNT_TRADE_MODE_REAL")
        actual = "mt5_live" if real else "mt5_demo"
        if self.expected_mode in ("mt5_demo", "mt5_live") and self.expected_mode != actual:
            raise Mt5ConfigError(
                f"Kontoen i MT5 er {'LIVE (ekte penger)' if real else 'DEMO'}, men "
                f"COPILOT_MODE={self.expected_mode}. Endre COPILOT_MODE eller logg inn på riktig konto."
            )
        self.resolved_mode = actual
        self.account = {
            "login": acc.login,
            "server": acc.server,
            "company": getattr(acc, "company", ""),
            "currency": acc.currency,
            "tradeMode": "live" if real else "demo",
            "leverage": getattr(acc, "leverage", None),
        }

    def _resolve_symbol_sync(self, canonical: str) -> str:
        mt5 = self._mt5
        candidates: list[str] = []
        if self._broker_symbol_cfg:
            candidates.append(self._broker_symbol_cfg)
        candidates.append(canonical)
        for name in candidates:
            if mt5.symbol_info(name) is not None:
                return name
        if not self._broker_symbol_cfg:
            for pattern in (f"*{canonical}*", "*GOLD*"):
                found = mt5.symbols_get(group=pattern) or ()
                names = sorted(
                    (s.name for s in found),
                    key=lambda n: (not n.upper().startswith(canonical[:3]), len(n)),
                )
                if names:
                    return names[0]
        raise Mt5ConfigError(
            f"Fant ikke symbolet {canonical} hos megleren. Sett COPILOT_MT5_SYMBOL til navnet "
            "som vises i Market Watch (f.eks. XAUUSD.m eller GOLD)."
        )

    def _detect_offset_sync(self, broker_symbol: str) -> None:
        mt5 = self._mt5
        if self._offset_cfg_ms is not None:
            self.offset_ms = self._offset_cfg_ms
            return
        first = mt5.symbol_info_tick(broker_symbol)
        deadline = time.monotonic() + 3.0
        while first is not None and time.monotonic() < deadline:
            time.sleep(0.25)
            tick = mt5.symbol_info_tick(broker_symbol)
            if tick is not None and tick.time_msc != first.time_msc:
                self.offset_ms = round_offset(tick.time_msc, self._wall_ms())
                self._save_offset()
                log.info("Detected broker UTC offset: %+d min", self.offset_ms // 60_000)
                return
        saved = self._load_offset()
        if saved is not None:
            self.offset_ms = saved
            self.warnings.append(
                "Markedet ser stengt ut; bruker sist kjente tidssone-forskyvning for megleren."
            )
        else:
            self.offset_ms = 0
            self.warnings.append(
                "Kunne ikke måle meglerens tidssone (ingen nye ticks). Tider kan være forskjøvet "
                "til markedet åpner. Sett COPILOT_MT5_UTC_OFFSET_MINUTES for å overstyre."
            )

    def _offset_path(self) -> Path | None:
        return None if self._data_dir is None else self._data_dir / OFFSET_FILE

    def _save_offset(self) -> None:
        p = self._offset_path()
        if p is None:
            return
        try:
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(json.dumps({"offset_ms": self.offset_ms}), encoding="utf-8")
        except OSError:
            log.warning("Could not persist broker UTC offset")

    def _load_offset(self) -> int | None:
        p = self._offset_path()
        try:
            if p is not None and p.exists():
                return int(json.loads(p.read_text(encoding="utf-8"))["offset_ms"])
        except (OSError, ValueError, KeyError):
            pass
        return None

    def _spec_sync(self, canonical: str) -> SymbolSpec:
        self.warnings = []
        self._connect_sync()
        mt5 = self._mt5
        broker = self._resolve_symbol_sync(canonical)
        if not mt5.symbol_select(broker, True):
            raise self._err(f"Kunne ikke aktivere {broker} i Market Watch")
        info = mt5.symbol_info(broker)
        if info is None:
            raise self._err(f"symbol_info({broker}) feilet")
        self._broker_symbol = broker
        self._detect_offset_sync(broker)
        return SymbolSpec(
            symbol=canonical,
            digits=int(info.digits),
            point=float(info.point),
            contract_size=float(info.trade_contract_size),
            volume_min=float(info.volume_min),
            volume_step=float(info.volume_step),
            volume_max=float(info.volume_max),
            currency_profit=str(info.currency_profit),
            description=str(getattr(info, "description", "")),
            source="mt5",
            tick_value=float(info.trade_tick_value),
            tick_size=float(info.trade_tick_size),
            tick_value_loss=float(getattr(info, "trade_tick_value_loss", 0) or 0) or None,
            broker_symbol=broker,
            currency_account=(self.account or {}).get("currency"),
        )

    # ---- MarketDataSource protocol ----------------------------------------
    async def symbol_spec(self, symbol: str) -> SymbolSpec:
        self._closed = False
        self._spec = await self._call(self._spec_sync, symbol)
        return self._spec

    def _to_utc(self, server_ms: int) -> int:
        return int(server_ms) - self.offset_ms

    def _rates_sync(self, tf: Timeframe, count: int) -> list[Candle]:
        mt5 = self._mt5
        code = {
            Timeframe.M1: _c(mt5, "TIMEFRAME_M1"),
            Timeframe.M5: _c(mt5, "TIMEFRAME_M5"),
            Timeframe.M15: _c(mt5, "TIMEFRAME_M15"),
            Timeframe.H1: _c(mt5, "TIMEFRAME_H1"),
        }[tf]
        rates = mt5.copy_rates_from_pos(self._broker_symbol, code, 0, count)
        if rates is None:
            raise self._err(f"copy_rates_from_pos {tf.value} feilet")
        point = self._spec.point if self._spec else 0.01
        out: list[Candle] = []
        n = len(rates)
        now_utc = self._wall_ms()
        for i in range(n):
            r = rates[i]
            start = self._to_utc(int(r["time"]) * 1000)
            out.append(
                Candle(
                    symbol=self._spec.symbol if self._spec else "XAUUSD",
                    timeframe=tf,
                    open_time_ms=start,
                    open=float(r["open"]),
                    high=float(r["high"]),
                    low=float(r["low"]),
                    close=float(r["close"]),
                    tick_count=int(r["tick_volume"]),
                    max_spread=float(r["spread"]) * point,
                    # The newest bar is still forming if its period has not ended.
                    closed=(i < n - 1) or (start + tf.ms <= now_utc),
                )
            )
        return out

    async def history(self, symbol: str, tf: Timeframe, count: int) -> list[Candle]:
        if self._broker_symbol is None:
            await self.symbol_spec(symbol)
        return await self._call(self._rates_sync, tf, count)

    def _poll_sync(self, from_msc: int) -> list[Any]:
        mt5 = self._mt5
        ticks = mt5.copy_ticks_from(
            self._broker_symbol, from_msc // 1000, TICK_BATCH, _c(mt5, "COPY_TICKS_INFO")
        )
        if ticks is None:
            raise self._err("copy_ticks_from feilet")
        return [ticks[i] for i in range(len(ticks))]

    def _health_sync(self) -> None:
        info = self._mt5.terminal_info()
        if info is None:
            raise self._err("MT5-terminalen svarer ikke")
        if not info.connected:
            raise Mt5Error("MT5-terminalen har mistet forbindelsen til megleren")

    def _last_tick_sync(self) -> Any:
        return self._mt5.symbol_info_tick(self._broker_symbol)

    async def ticks(self, symbol: str) -> AsyncIterator[Tick]:
        if self._broker_symbol is None:
            await self.symbol_spec(symbol)
        canonical = self._spec.symbol if self._spec else symbol
        last = await self._call(self._last_tick_sync)
        last_msc = int(last.time_msc) if last is not None else (self._wall_ms() + self.offset_ms)
        seen_at_last = 1 if last is not None else 0
        prev_bid = float(last.bid) if last is not None and last.bid else None
        prev_ask = float(last.ask) if last is not None and last.ask else None
        if prev_bid and prev_ask and prev_ask >= prev_bid:
            # Emit the last known price immediately, even when the market is closed,
            # so the panel shows something; the hub marks it stale by its timestamp.
            yield Tick(canonical, self._to_utc(last_msc), prev_bid, prev_ask, 1.0)
        last_health = time.monotonic()
        while not self._closed:
            batch = await self._call(self._poll_sync, last_msc)
            new, last_msc, seen_at_last = select_new_ticks(batch, last_msc, seen_at_last)
            for t in new:
                bid = float(t["bid"]) or prev_bid
                ask = float(t["ask"]) or prev_ask
                if not bid or not ask or ask < bid:
                    continue
                prev_bid, prev_ask = bid, ask
                yield Tick(canonical, self._to_utc(int(t["time_msc"])), bid, ask, 1.0)
            if time.monotonic() - last_health > 5.0:
                await self._call(self._health_sync)
                last_health = time.monotonic()
            if len(batch) < TICK_BATCH:
                await asyncio.sleep(self._poll)

    # ---- account & positions (read-only) -------------------------------------
    def _account_sync(self, day_start_utc_ms: int) -> dict[str, Any] | None:
        mt5 = self._mt5
        acc = mt5.account_info()
        if acc is None:
            return None
        positions = []
        specs: dict[str, dict[str, Any]] = {}
        for p in mt5.positions_get() or ():
            sym = p.symbol
            if sym not in specs:
                info = mt5.symbol_info(sym)
                tick = mt5.symbol_info_tick(sym)
                specs[sym] = {
                    "digits": int(getattr(info, "digits", 2)) if info else 2,
                    "contractSize": float(getattr(info, "trade_contract_size", 0) or 0) if info else 0.0,
                    "tickSize": float(getattr(info, "trade_tick_size", 0) or 0) if info else 0.0,
                    "tickValue": float(getattr(info, "trade_tick_value", 0) or 0) if info else 0.0,
                    "tickValueLoss": float(getattr(info, "trade_tick_value_loss", 0) or 0) if info else 0.0,
                    "bid": float(tick.bid) if tick else None,
                    "ask": float(tick.ask) if tick else None,
                }
            positions.append(
                {
                    "ticket": int(p.ticket),
                    "symbol": sym,
                    "type": "buy" if p.type == _c(mt5, "POSITION_TYPE_BUY") else "sell",
                    "volume": float(p.volume),
                    "priceOpen": float(p.price_open),
                    "priceCurrent": float(p.price_current),
                    "sl": float(p.sl or 0),
                    "tp": float(p.tp or 0),
                    "profit": float(p.profit),
                    "swap": float(getattr(p, "swap", 0) or 0),
                    "timeMs": self._to_utc(int(getattr(p, "time_msc", 0) or int(p.time) * 1000)),
                    "comment": str(getattr(p, "comment", "") or ""),
                    "spec": specs[sym],
                }
            )
        # Realized result today: all trade deals since local midnight (server-time scale).
        start_s = (day_start_utc_ms + self.offset_ms) // 1000
        end_s = (self._wall_ms() + self.offset_ms) // 1000 + 3600
        realized = 0.0
        closed = 0
        trade_types = {_c(mt5, "DEAL_TYPE_BUY"), _c(mt5, "DEAL_TYPE_SELL")}
        for d in mt5.history_deals_get(start_s, end_s) or ():
            if d.type not in trade_types:
                continue  # deposits, withdrawals, credit etc.
            realized += (
                float(d.profit)
                + float(getattr(d, "swap", 0) or 0)
                + float(getattr(d, "commission", 0) or 0)
                + float(getattr(d, "fee", 0) or 0)
            )
            if getattr(d, "entry", 0) in (1, 2, 3):  # OUT, INOUT, OUT_BY
                closed += 1
        orders = mt5.orders_get()
        return {
            "account": {
                "login": acc.login,
                "currency": acc.currency,
                "balance": float(acc.balance),
                "equity": float(acc.equity),
                "profit": float(acc.profit),
                "margin": float(acc.margin),
                "marginFree": float(acc.margin_free),
                "marginLevel": float(acc.margin_level or 0),
                "tradeMode": "live" if acc.trade_mode == _c(mt5, "ACCOUNT_TRADE_MODE_REAL") else "demo",
            },
            "positions": positions,
            "pendingOrders": len(orders or ()),
            "dayRealized": realized,
            "dayClosedDeals": closed,
        }

    async def account_snapshot(self, day_start_utc_ms: int) -> dict[str, Any] | None:
        """Account, open positions and today's realized P/L. Read-only."""
        if self._mt5 is None or self._broker_symbol is None:
            return None
        return await self._call(self._account_sync, day_start_utc_ms)

    # ---- history for the journal, coach and replay (read-only) -----------------
    def _ensure_mt5(self) -> Any:
        if self._mt5 is None:
            raise Mt5Error("MT5 er ikke tilkoblet ennå")
        return self._mt5

    def _deals_sync(self, from_utc_ms: int, to_utc_ms: int) -> list[dict[str, Any]]:
        mt5 = self._ensure_mt5()
        a = (from_utc_ms + self.offset_ms) // 1000
        b = (to_utc_ms + self.offset_ms) // 1000 + 1
        out = []
        for d in mt5.history_deals_get(a, b) or ():
            out.append(
                {
                    "ticket": int(d.ticket),
                    "order": int(getattr(d, "order", 0) or 0),
                    "positionId": int(getattr(d, "position_id", 0) or 0),
                    "timeMs": self._to_utc(int(getattr(d, "time_msc", 0) or int(d.time) * 1000)),
                    "type": int(d.type),
                    "entry": int(getattr(d, "entry", 0) or 0),
                    "reason": int(getattr(d, "reason", 0) or 0),
                    "symbol": str(d.symbol),
                    "volume": float(d.volume),
                    "price": float(d.price),
                    "profit": float(d.profit),
                    "commission": float(getattr(d, "commission", 0) or 0),
                    "swap": float(getattr(d, "swap", 0) or 0),
                    "fee": float(getattr(d, "fee", 0) or 0),
                    "magic": int(getattr(d, "magic", 0) or 0),
                    "comment": str(getattr(d, "comment", "") or ""),
                }
            )
        return out

    async def history_deals(self, from_utc_ms: int, to_utc_ms: int) -> list[dict[str, Any]]:
        return await self._call(self._deals_sync, from_utc_ms, to_utc_ms)

    def _orders_sync(self, position_id: int) -> list[dict[str, Any]]:
        mt5 = self._ensure_mt5()
        out = []
        for o in mt5.history_orders_get(position=position_id) or ():
            out.append(
                {
                    "ticket": int(o.ticket),
                    "sl": float(getattr(o, "sl", 0) or 0),
                    "tp": float(getattr(o, "tp", 0) or 0),
                    "timeMs": self._to_utc(int(getattr(o, "time_setup_msc", 0) or int(o.time_setup) * 1000)),
                }
            )
        return out

    async def history_orders(self, position_id: int) -> list[dict[str, Any]]:
        return await self._call(self._orders_sync, position_id)

    def _symbol_name(self, symbol: str) -> str:
        return (
            self._broker_symbol
            if self._spec and symbol == self._spec.symbol and self._broker_symbol
            else symbol
        )

    def _rows_to_candles(self, rows: Any, tf: Timeframe, symbol: str, point: float) -> list[Candle]:
        out = []
        for i in range(len(rows) if rows is not None else 0):
            r = rows[i]
            out.append(
                Candle(
                    symbol=symbol,
                    timeframe=tf,
                    open_time_ms=self._to_utc(int(r["time"]) * 1000),
                    open=float(r["open"]),
                    high=float(r["high"]),
                    low=float(r["low"]),
                    close=float(r["close"]),
                    tick_count=int(r["tick_volume"]),
                    max_spread=float(r["spread"]) * point,
                    closed=True,
                )
            )
        return out

    def _rates_before_sync(self, symbol: str, tf: Timeframe, until_utc_ms: int, count: int) -> list[Candle]:
        mt5 = self._ensure_mt5()
        code = (
            _c(mt5, _TF_CODES[tf.value])
            if hasattr(mt5, _TF_CODES[tf.value])
            else _DEFAULTS[_TF_CODES[tf.value]]
        )
        rows = mt5.copy_rates_from(
            self._symbol_name(symbol), code, (until_utc_ms + self.offset_ms) // 1000, count + 1
        )
        point = self._spec.point if self._spec else 0.01
        # Only bars that had fully closed at `until` - never the bar containing it (no look-ahead).
        return [
            c
            for c in self._rows_to_candles(rows, tf, symbol, point)
            if c.open_time_ms + tf.ms <= until_utc_ms
        ][-count:]

    async def rates_before(self, symbol: str, tf: Timeframe, until_utc_ms: int, count: int) -> list[Candle]:
        return await self._call(self._rates_before_sync, symbol, tf, until_utc_ms, count)

    def _rates_range_sync(self, symbol: str, tf: Timeframe, from_utc_ms: int, to_utc_ms: int) -> list[Candle]:
        mt5 = self._ensure_mt5()
        code = (
            _c(mt5, _TF_CODES[tf.value])
            if hasattr(mt5, _TF_CODES[tf.value])
            else _DEFAULTS[_TF_CODES[tf.value]]
        )
        rows = mt5.copy_rates_range(
            self._symbol_name(symbol),
            code,
            (from_utc_ms + self.offset_ms) // 1000,
            (to_utc_ms + self.offset_ms) // 1000,
        )
        point = self._spec.point if self._spec else 0.01
        return self._rows_to_candles(rows, tf, symbol, point)

    async def rates_range(self, symbol: str, tf: Timeframe, from_utc_ms: int, to_utc_ms: int) -> list[Candle]:
        return await self._call(self._rates_range_sync, symbol, tf, from_utc_ms, to_utc_ms)

    def _ticks_range_sync(self, symbol: str, from_utc_ms: int, to_utc_ms: int) -> list[Tick]:
        mt5 = self._ensure_mt5()
        rows = mt5.copy_ticks_range(
            self._symbol_name(symbol),
            (from_utc_ms + self.offset_ms) // 1000,
            (to_utc_ms + self.offset_ms) // 1000 + 1,
            _c(mt5, "COPY_TICKS_INFO"),
        )
        out: list[Tick] = []
        bid = ask = None
        for i in range(len(rows) if rows is not None else 0):
            r = rows[i]
            bid = float(r["bid"]) or bid
            ask = float(r["ask"]) or ask
            t = self._to_utc(int(r["time_msc"]))
            if bid and ask and ask >= bid and from_utc_ms <= t <= to_utc_ms:
                out.append(Tick(symbol, t, bid, ask, 1.0))
        return out

    async def ticks_range(self, symbol: str, from_utc_ms: int, to_utc_ms: int) -> list[Tick]:
        """Real historical bid/ask ticks (broker history depth varies, often months)."""
        return await self._call(self._ticks_range_sync, symbol, from_utc_ms, to_utc_ms)

    async def close(self) -> None:
        self._closed = True
        self._broker_symbol = None
        if self._mt5 is not None:
            mt5 = self._mt5
            try:
                await self._call(mt5.shutdown)
            except Exception:  # noqa: BLE001
                pass


def select_new_ticks(batch: list[Any], last_msc: int, seen_at_last: int) -> tuple[list[Any], int, int]:
    """Return ticks not yet delivered, given the last delivered timestamp.

    ``copy_ticks_from`` has 1-second request granularity, so each poll returns
    some ticks we already have. Several ticks can share one millisecond; we
    remember how many at ``last_msc`` were already delivered.
    """
    same = [t for t in batch if int(t["time_msc"]) == last_msc]
    newer = sorted((t for t in batch if int(t["time_msc"]) > last_msc), key=lambda t: int(t["time_msc"]))
    new = same[seen_at_last:] + newer
    if newer:
        last_msc = int(newer[-1]["time_msc"])
        seen_at_last = sum(1 for t in newer if int(t["time_msc"]) == last_msc)
    else:
        seen_at_last = max(seen_at_last, len(same))
    return new, last_msc, seen_at_last
