"""MT5 source against a fake MetaTrader5 module (the real one is Windows-only)."""

import asyncio
from types import SimpleNamespace

import pytest

from app.hub import MarketHub
from app.market.models import Timeframe
from app.market.mt5_source import Mt5ConfigError, Mt5Error, Mt5MarketSource, round_offset, select_new_ticks

OFFSET = 2 * 3_600_000  # broker server time = UTC+2
UTC_NOW = 1_793_500_000_000


class FakeMT5:
    ACCOUNT_TRADE_MODE_REAL = 2

    def __init__(self, trade_mode=0, symbols=("XAUUSD.m",), live=True):
        self.trade_mode = trade_mode
        self.symbols = set(symbols)
        self.connected = True
        self.init_ok = True
        self.server_now = UTC_NOW + OFFSET
        self.live = live
        self.ticks = []
        self.calls = []

    def _log(self, name):
        self.calls.append(name)

    def initialize(self, **kw):
        self._log("initialize")
        return self.init_ok

    def shutdown(self):
        self._log("shutdown")

    def last_error(self):
        return (-10004, "No IPC connection")

    positions = ()
    deals = ()
    orders = ()

    def account_info(self):
        return SimpleNamespace(login=123, server="Broker-Demo", company="Broker", currency="NOK",
                               trade_mode=self.trade_mode, leverage=100, balance=10_000.0, equity=9_950.0,
                               profit=-50.0, margin=400.0, margin_free=9_550.0, margin_level=2487.5)

    def positions_get(self):
        return self.positions

    def orders_get(self):
        return self.orders

    def history_deals_get(self, date_from, date_to):
        self.deal_query = (date_from, date_to)
        return self.deals

    hist_orders = {}

    def history_orders_get(self, position=None):
        return self.hist_orders.get(position, ())

    def copy_rates_from(self, name, tf, date_from, count):
        minute = 60
        last = (date_from // minute) * minute
        return [{"time": last - (count - 1 - i) * minute, "open": 4000.0, "high": 4001.0, "low": 3999.0,
                 "close": 4000.5, "tick_volume": 50, "spread": 25, "real_volume": 0} for i in range(count)]

    def copy_rates_range(self, name, tf, date_from, date_to):
        return [{"time": t, "open": 4000.0, "high": 4001.0, "low": 3999.0, "close": 4000.5, "tick_volume": 50,
                 "spread": 25, "real_volume": 0} for t in range((date_from // 60) * 60, date_to, 60)]

    def copy_ticks_range(self, name, date_from, date_to, flags):
        return [t for t in self.ticks if date_from * 1000 <= t["time_msc"] <= date_to * 1000]

    def terminal_info(self):
        return SimpleNamespace(connected=self.connected)

    def symbol_info(self, name):
        if name not in self.symbols:
            return None
        return SimpleNamespace(name=name, digits=2, point=0.01, trade_contract_size=100.0, volume_min=0.01,
                               volume_step=0.01, volume_max=50.0, currency_profit="USD", description="Gold",
                               trade_tick_value=9.9, trade_tick_size=0.01, trade_tick_value_loss=10.0)

    def symbols_get(self, group=""):
        pat = group.strip("*")
        return [SimpleNamespace(name=n) for n in self.symbols if pat in n]

    def symbol_select(self, name, enable):
        return name in self.symbols

    def symbol_info_tick(self, name):
        if self.live:
            self.server_now += 300
        return SimpleNamespace(time_msc=self.server_now, bid=4000.0, ask=4000.25)

    def copy_rates_from_pos(self, name, tf, start, count):
        minute = 60_000
        last = (self.server_now // minute) * minute
        rows = []
        for i in range(count):
            t = last - (count - 1 - i) * minute
            rows.append({"time": t // 1000, "open": 4000.0, "high": 4001.0, "low": 3999.0, "close": 4000.5,
                         "tick_volume": 50, "spread": 25, "real_volume": 0})
        return rows

    def copy_ticks_from(self, name, from_sec, count, flags):
        return [t for t in self.ticks if t["time_msc"] >= from_sec * 1000][:count]


def make(fake, **kw):
    kw.setdefault("wall_ms", lambda: UTC_NOW)
    return Mt5MarketSource(module_loader=lambda: fake, poll_interval=0.001, **kw)


def test_spec_symbol_resolution_offset_and_account():
    fake = FakeMT5()

    async def run():
        src = make(fake)
        spec = await src.symbol_spec("XAUUSD")
        assert spec.broker_symbol == "XAUUSD.m"
        assert spec.contract_size == 100.0 and spec.tick_value == 9.9 and spec.currency_account == "NOK"
        assert spec.source == "mt5"
        assert src.offset_ms == OFFSET
        assert src.resolved_mode == "mt5_demo"
        assert src.account["currency"] == "NOK"
        await src.close()

    asyncio.run(run())


def test_live_account_rejected_when_demo_expected():
    async def run():
        src = make(FakeMT5(trade_mode=2), expected_mode="mt5_demo")
        with pytest.raises(Mt5ConfigError, match="LIVE"):
            await src.symbol_spec("XAUUSD")
        src2 = make(FakeMT5(trade_mode=2), expected_mode="mt5")
        await src2.symbol_spec("XAUUSD")
        assert src2.resolved_mode == "mt5_live"

    asyncio.run(run())


def test_terminal_not_running():
    fake = FakeMT5()
    fake.init_ok = False

    async def run():
        with pytest.raises(Mt5Error, match="MetaTrader 5"):
            await make(fake).symbol_spec("XAUUSD")

    asyncio.run(run())


def test_unknown_symbol_is_config_error():
    async def run():
        with pytest.raises(Mt5ConfigError):
            await make(FakeMT5(symbols=("EURUSD",))).symbol_spec("XAUUSD")

    asyncio.run(run())


def test_closed_market_uses_saved_offset(tmp_path):
    async def run():
        src = make(FakeMT5(), data_dir=tmp_path)
        await src.symbol_spec("XAUUSD")  # detects + saves offset
        src2 = make(FakeMT5(live=False), data_dir=tmp_path)
        await src2.symbol_spec("XAUUSD")
        assert src2.offset_ms == OFFSET and src2.warnings
        src3 = make(FakeMT5(live=False), utc_offset_minutes=180)
        await src3.symbol_spec("XAUUSD")
        assert src3.offset_ms == 3 * 3_600_000 and not src3.warnings

    asyncio.run(run())


def test_history_converted_to_utc_and_forming_bar():
    async def run():
        src = make(FakeMT5())
        bars = await src.history("XAUUSD", Timeframe.M1, 10)
        assert len(bars) == 10
        assert bars[-1].open_time_ms % 60_000 == 0
        assert abs(bars[-1].open_time_ms - UTC_NOW) < 120_000  # UTC, not server time
        assert all(b.closed for b in bars[:-1]) and not bars[-1].closed
        assert bars[0].max_spread == pytest.approx(0.25)

    asyncio.run(run())


def test_tick_stream_dedupes_and_converts_time():
    fake = FakeMT5()

    async def run():
        src = make(fake)
        await src.symbol_spec("XAUUSD")
        fake.live = False  # freeze the fake clock so the start tick is deterministic
        start = fake.server_now
        fake.ticks = [
            {"time_msc": start - 10, "bid": 3999.0, "ask": 3999.2},  # older than start: skipped
            {"time_msc": start + 5, "bid": 4000.1, "ask": 4000.3},
            {"time_msc": start + 5, "bid": 4000.2, "ask": 0.0},  # same ms, ask unchanged -> carried
            {"time_msc": start + 900, "bid": 4000.4, "ask": 4000.6},
        ]
        got = []
        agen = src.ticks("XAUUSD")

        async def collect():
            async for t in agen:
                got.append(t)
                if len(got) == 4:
                    break

        await asyncio.wait_for(collect(), timeout=5)
        await agen.aclose()
        # first the last known price (symbol_info_tick), then only new ticks
        assert [t.bid for t in got] == [4000.0, 4000.1, 4000.2, 4000.4]
        assert got[0].time_ms == start - OFFSET
        assert got[2].ask == 4000.3
        assert got[1].time_ms == start + 5 - OFFSET
        assert got[0].symbol == "XAUUSD"

    asyncio.run(run())


def test_select_new_ticks_same_millisecond():
    b = [{"time_msc": 100}, {"time_msc": 100}, {"time_msc": 101}]
    new, last, seen = select_new_ticks(b, 100, 1)
    assert [t["time_msc"] for t in new] == [100, 101] and (last, seen) == (101, 1)
    new, last, seen = select_new_ticks(b, 101, 1)
    assert new == [] and (last, seen) == (101, 1)


def test_round_offset():
    assert round_offset(UTC_NOW + 3 * 3_600_000 + 4_000, UTC_NOW) == 3 * 3_600_000
    assert round_offset(UTC_NOW - 5 * 3_600_000 - 70_000, UTC_NOW) == -5 * 3_600_000


def test_hub_with_mt5_seeds_history_and_reports_account():
    fake = FakeMT5()

    async def run():
        src = make(fake)
        hub = MarketHub(src, "XAUUSD", "mt5", initial_backoff_seconds=0.01)
        await hub.start()
        for _ in range(200):
            await asyncio.sleep(0.01)
            if hub.candles(Timeframe.H1):
                break
        assert hub.mode == "mt5_demo"
        assert len(hub.candles(Timeframe.M1)) > 100
        status = hub.status_payload()
        assert status["account"]["tradeMode"] == "demo" and status["synthetic"] is False
        fake.connected = False  # broker connection lost -> error surfaces
        await hub.stop()

    asyncio.run(run())


def test_terminal_disconnect_raises():
    fake = FakeMT5()
    fake.connected = False

    async def run():
        src = make(fake)
        await src.symbol_spec("XAUUSD")
        with pytest.raises(Mt5Error, match="forbindelsen"):
            src._health_sync()

    asyncio.run(run())


def test_account_snapshot_reads_positions_and_todays_deals():
    fake = FakeMT5()
    opened = fake.server_now - 60_000
    fake.positions = (
        SimpleNamespace(ticket=7, symbol="XAUUSD.m", type=0, volume=0.1, price_open=4000.0, price_current=3999.0,
                        sl=3998.0, tp=4004.0, profit=-100.0, swap=0.0, time=0, time_msc=opened,
                        comment=""),
    )
    fake.deals = (
        SimpleNamespace(type=0, entry=0, profit=0.0, swap=0.0, commission=-7.0, fee=0.0),  # entry
        SimpleNamespace(type=1, entry=1, profit=-200.0, swap=0.0, commission=-7.0, fee=0.0),  # close
        SimpleNamespace(type=2, entry=0, profit=5000.0, swap=0.0, commission=0.0, fee=0.0),  # deposit: ignored
    )

    async def run():
        src = make(fake)
        await src.symbol_spec("XAUUSD")
        snap = await src.account_snapshot(UTC_NOW - 3_600_000)
        assert snap["account"]["balance"] == 10_000.0 and snap["account"]["tradeMode"] == "demo"
        p = snap["positions"][0]
        assert p["type"] == "buy" and p["spec"]["tickValueLoss"] == 10.0
        assert p["timeMs"] == opened - OFFSET
        assert snap["dayRealized"] == -214.0 and snap["dayClosedDeals"] == 1
        # query window is in server time
        assert fake.deal_query[0] == (UTC_NOW - 3_600_000 + OFFSET) // 1000

    asyncio.run(run())


def test_rates_before_excludes_bar_containing_the_entry():
    fake = FakeMT5()

    async def run():
        src = make(fake)
        await src.symbol_spec("XAUUSD")
        entry = UTC_NOW - (UTC_NOW % 60_000) + 30_000  # 30 s into a minute
        bars = await src.rates_before("XAUUSD", Timeframe.M1, entry, 10)
        assert len(bars) == 10
        assert all(b.open_time_ms + 60_000 <= entry for b in bars)  # no look-ahead
        assert bars[-1].open_time_ms == entry - 30_000 - 60_000

    asyncio.run(run())
