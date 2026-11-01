import pytest

from app.account.risk import RiskRules, build_account_view, enrich_position, money_per_price_unit

XAU = {"digits": 2, "contractSize": 100.0, "tickSize": 0.01, "tickValue": 1.0, "tickValueLoss": 1.0}
RULES = RiskRules(max_per_trade_pct=1.0, daily_loss_limit_pct=3.0, near_sl_fraction=0.25)


def pos(ticket=1, typ="buy", vol=0.1, open_=4000.0, cur=4000.5, sl=3998.0, tp=4004.0, profit=5.0, sym="XAUUSD"):
    return {"ticket": ticket, "symbol": sym, "type": typ, "volume": vol, "priceOpen": open_, "priceCurrent": cur,
            "sl": sl, "tp": tp, "profit": profit, "swap": 0.0, "timeMs": 0, "comment": "", "spec": XAU}


def raw(positions, balance=1000.0, realized=0.0, margin_level=5000.0):
    return {"account": {"balance": balance, "equity": balance, "currency": "USD", "marginLevel": margin_level},
            "positions": positions, "pendingOrders": 0, "dayRealized": realized, "dayClosedDeals": 0}


def test_money_per_price_unit_uses_contract_spec():
    # 0.10 lot of 100 oz = 10 oz -> 10 USD per 1 USD move
    assert money_per_price_unit(XAU, 0.1) == pytest.approx(10.0)
    assert money_per_price_unit({"tickSize": 0, "tickValue": 1}, 1) is None


def test_10_oz_with_2_usd_stop_risks_20_usd():
    p = enrich_position(pos(), balance=1000.0, rules=RULES, atr=1.5)
    assert p["oz"] == 10.0
    assert p["riskMoney"] == pytest.approx(20.0)
    assert p["riskPct"] == pytest.approx(2.0)
    assert p["toSlMoney"] == pytest.approx(25.0)  # from 4000.5 down to 3998
    assert p["rMultiple"] == pytest.approx(0.25)
    # 10 lots is 100x more
    assert enrich_position(pos(vol=10.0), 1000.0, RULES, None)["riskMoney"] == pytest.approx(2000.0)


def test_short_and_locked_profit():
    s = enrich_position(pos(typ="sell", open_=4000, cur=3999, sl=4002, tp=3995), 1000, RULES, None)
    assert s["riskMoney"] == pytest.approx(20.0) and s["distToSl"] == pytest.approx(3.0)
    be = enrich_position(pos(sl=4001.0, cur=4003.0), 1000, RULES, None)
    assert be["riskMoney"] is None and be["lockedMoney"] == pytest.approx(10.0)


def test_alerts_risk_no_sl_near_sl():
    v = build_account_view(raw([pos(ticket=1), pos(ticket=2, sl=0)]), RULES)
    keys = {a["key"].split(":")[0] for a in v["alerts"]}
    assert {"risk", "nosl", "corr"} <= keys
    assert v["alerts"][0]["level"] == "critical"  # no SL sorted first
    text = next(a["text"] for a in v["alerts"] if a["key"] == "risk:1")
    assert text.startswith("XAUUSD long 0,10 lot risikerer 2,0 % av kontoen")
    near = build_account_view(raw([pos(cur=3998.4)]), RULES, {"XAUUSD": 1.5})
    assert any(a["kind"] == "sl" for a in near["alerts"])


def test_daily_loss_limit():
    # start balance 1000, limit 3 % = 30
    reached = build_account_view(raw([], balance=965.0, realized=-35.0), RULES)
    assert reached["day"]["limitMoney"] == pytest.approx(30.0)
    assert any(a["key"] == "daily:reached" for a in reached["alerts"])
    near = build_account_view(raw([], balance=975.0, realized=-25.0), RULES)
    assert any(a["key"] == "daily:near" for a in near["alerts"])
    open_risk = build_account_view(raw([pos(vol=0.2, profit=0.0)], balance=985.0, realized=-15.0), RULES)
    assert any(a["key"] == "daily:open" for a in open_risk["alerts"])  # -15 - 40 risk > 30
    ok = build_account_view(raw([], balance=1000.0), RULES)
    assert ok["alerts"] == [] and ok["day"]["usedPct"] == 0


def test_spread_and_margin_alerts():
    v = build_account_view(raw([pos(vol=0.05)], margin_level=150.0), RULES, None, {"XAUUSD"})
    kinds = {a["key"] for a in v["alerts"]}
    assert "margin:low" in kinds and "spread:XAUUSD" in kinds


def test_monitor_publishes_unavailable_for_demo_and_view_for_mt5():
    import asyncio

    from app.account.monitor import AccountMonitor
    from app.hub import MarketHub
    from app.market.demo import DemoMarketSource

    class Src(DemoMarketSource):
        async def account_snapshot(self, day_start_ms):
            return raw([pos()])

    class An:
        last = {"timeframes": {"1m": {"atr": 1.5}}, "spread": {"state": "normal"}}

    async def run():
        demo = MarketHub(DemoMarketSource(seed=1, realtime=False), "XAUUSD", "demo")
        m = AccountMonitor(demo, An(), RULES)
        await m.step()
        assert m.last["available"] is False
        hub = MarketHub(Src(seed=1, realtime=False), "XAUUSD", "mt5")
        sub = hub.subscribe()
        m2 = AccountMonitor(hub, An(), RULES)
        await m2.step()
        await m2.step()  # unchanged -> not re-published
        msgs = [sub.queue.get_nowait() for _ in range(sub.queue.qsize())]
        assert [x["type"] for x in msgs] == ["account"]
        assert msgs[0]["data"]["positions"][0]["riskMoney"] == 20.0
        assert any(x["type"] == "account" for x in hub.snapshot())  # retained

    asyncio.run(run())
