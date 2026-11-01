import time

import pytest
from fastapi.testclient import TestClient

from app.journal.build import build_trades
from app.journal.stats import bootstrap_ci, bootstrap_diff_ci, compute_stats, wilson
from app.journal.store import JournalStore

SPEC = {"XAUUSD": {"tickSize": 0.01, "tickValue": 1.0, "contractSize": 100.0}}
T0 = 1_793_000_000_000


def deal(ticket, pos, t, typ, entry, price, vol=0.1, profit=0.0, commission=-0.7, reason=0, sym="XAUUSD"):
    return {"ticket": ticket, "position_id": pos, "order_ticket": ticket, "time_ms": t, "type": typ, "entry": entry,
            "reason": reason, "symbol": sym, "volume": vol, "price": price, "profit": profit,
            "commission": commission, "swap": 0.0, "fee": 0.0}


def test_build_round_trip_trades():
    deals = [
        deal(1, 10, T0, 0, 0, 4000.0),  # buy in
        deal(2, 10, T0 + 60_000, 1, 1, 4004.0, profit=40.0, reason=5),  # sell out at TP
        deal(3, 11, T0 + 120_000, 1, 0, 4003.0, vol=0.2),  # short in, two partial exits
        deal(4, 11, T0 + 180_000, 0, 1, 4004.0, vol=0.1, profit=-10.0),
        deal(5, 11, T0 + 240_000, 0, 1, 4005.0, vol=0.1, profit=-20.0, reason=4),
        deal(6, 12, T0 + 300_000, 0, 0, 4006.0),  # still open
        {**deal(7, 0, T0, 2, 0, 0.0, profit=1000.0)},  # balance deposit, ignored
    ]
    levels = {10: {"sl": 3998.0, "tp": 4004.0}, 11: {"sl": 4005.0, "tp": None}}
    tr = {t["position_id"]: t for t in build_trades(deals, levels, SPEC)}
    a = tr[10]
    assert a["direction"] == "long" and a["closed"] == 1 and a["exit_reason"] == "tp"
    assert a["net"] == pytest.approx(38.6) and a["risk_money"] == pytest.approx(20.0)
    assert a["r_multiple"] == pytest.approx(38.6 / 20.0, abs=1e-3)
    b = tr[11]
    assert b["direction"] == "short" and b["exit_price"] == pytest.approx(4004.5) and b["exit_reason"] == "sl"
    assert b["risk_money"] == pytest.approx(40.0) and b["r_multiple"] == pytest.approx(-32.1 / 40.0, abs=1e-3)
    assert tr[12]["closed"] == 0 and tr[12]["r_multiple"] is None
    assert 0 not in tr


def test_store_is_idempotent_and_keeps_notes_separate(tmp_path):
    s = JournalStore(tmp_path / "j.db", tmp_path / "shots")
    raw = [{"ticket": 1, "positionId": 10, "order": 1, "timeMs": T0, "type": 0, "entry": 0, "reason": 0,
            "symbol": "XAUUSD", "volume": 0.1, "price": 4000.0, "profit": 0.0, "commission": 0.0, "swap": 0.0,
            "fee": 0.0}]
    assert s.insert_deals(raw) == 1
    assert s.insert_deals(raw) == 0  # duplicate journal entry prevented
    s.set_levels(10, None, None, "live")
    s.set_levels(10, 3998.0, None, "live")  # first SL seen upgrades an SL-less record
    s.set_levels(10, 3990.0, None, "live")  # later moves don't change the initial SL
    assert s.levels()[10]["sl"] == 3998.0
    s.set_levels(10, 3997.0, 4005.0, "order")  # entry order is authoritative
    assert s.levels()[10]["sl"] == 3997.0
    s.replace_trades(build_trades(s.deals(), s.levels(), SPEC))
    s.update_notes(10, note="God entry", setup="pullback", tags=["London", " A+ ", ""])
    t = s.trade(10)
    assert t["note"] == "God entry" and t["setup"] == "pullback" and t["tags"] == ["A+", "London"]
    s.replace_trades(build_trades(s.deals(), s.levels(), SPEC))  # rebuild must not lose notes
    assert s.trade(10)["note"] == "God entry"


def test_stats():
    trades = []
    nets = [20, -10, 30, -10, -10, 25, 0, -5]
    for i, n in enumerate(nets):
        trades.append({"position_id": i, "symbol": "XAUUSD", "direction": "long" if i % 2 else "short",
                       "open_ms": T0 + i * 3_600_000, "close_ms": T0 + i * 3_600_000 + 600_000, "net": float(n),
                       "commission": -0.7, "swap": 0.0, "fee": 0.0, "r_multiple": n / 10, "closed": 1,
                       "session": "London", "setup": "pullback" if i < 4 else "", "context": None})
    st = compute_stats(trades)
    s = st["summary"]
    assert s["n"] == 8 and s["wins"] == 3 and s["losses"] == 4
    assert s["net"] == 40.0 and s["profitFactor"] == pytest.approx(75 / 35, abs=0.01)
    assert s["avgWin"] == 25.0 and s["avgLoss"] == -8.75
    assert s["maxDrawdown"] == 20.0  # 40 -> 20
    assert s["streaks"]["maxLosses"] == 2 and s["streaks"]["maxWins"] == 1
    assert s["expectancyR"] == pytest.approx(0.5)
    assert st["costs"]["commission"] == pytest.approx(-5.6)
    assert {g["key"] for g in st["bySetup"]} == {"pullback", "(uten tag)"}
    assert st["equity"][-1]["equity"] == 40.0 and st["daily"]
    assert compute_stats([])["empty"] is True


def test_statistical_helpers():
    lo, hi = wilson(5, 10)
    assert lo < 0.5 < hi and wilson(0, 0) is None
    ci = bootstrap_ci([1.0] * 20)
    assert ci == (1.0, 1.0)
    d = bootstrap_diff_ci([1.0, 1.2, 0.8, 1.1] * 10, [0.0, 0.1, -0.1, 0.05] * 10)
    assert d[0] > 0.8 and d[1] < 1.2


# ---- service + API against a fake MT5 -------------------------------------------------
def test_journal_sync_and_api(tmp_path):
    from app.config import Settings
    from app.main import create_app
    from app.market.mt5_source import Mt5MarketSource

    from .conftest import EXT_ID, TOKEN
    from .test_mt5_source import OFFSET, FakeMT5

    fake = FakeMT5(live=False)
    fake.server_now = int(time.time() * 1000) + OFFSET
    t_open = fake.server_now - 7_200_000
    from types import SimpleNamespace as NS

    fake.deals = (
        NS(ticket=1, order=1, position_id=10, time=0, time_msc=t_open, type=0, entry=0, reason=0, symbol="XAUUSD.m",
           volume=0.1, price=4000.0, profit=0.0, commission=-0.7, swap=0.0, fee=0.0, magic=0, comment=""),
        NS(ticket=2, order=2, position_id=10, time=0, time_msc=t_open + 300_000, type=1, entry=1, reason=5,
           symbol="XAUUSD.m", volume=0.1, price=4004.0, profit=400.0, commission=-0.7, swap=0.0, fee=0.0, magic=0,
           comment=""),
    )
    fake.hist_orders = {10: (NS(ticket=1, sl=3998.0, tp=4004.0, time_setup=0, time_setup_msc=t_open),)}
    settings = Settings(data_dir=tmp_path, auth_token=TOKEN, allowed_extension_ids=[EXT_ID], ai_enabled=False,
                        anthropic_api_key=None, mode="mt5")
    src = Mt5MarketSource(module_loader=lambda: fake, poll_interval=0.01, utc_offset_minutes=OFFSET // 60_000,
                          data_dir=tmp_path)
    app = create_app(settings, source=src)
    auth = {"Authorization": f"Bearer {TOKEN}"}
    with TestClient(app) as c:
        for _ in range(100):
            if app.state.hub.spec is not None:
                break
            time.sleep(0.02)
        r = c.post("/api/journal/sync", headers=auth).json()
        assert r["trades"] == 1 and r["newDeals"] == 2
        assert c.post("/api/journal/sync", headers=auth).json()["newDeals"] == 0  # idempotent
        trades = c.get("/api/journal/trades", headers=auth).json()["trades"]
        t = trades[0]
        assert t["sl"] == 3998.0 and t["exit_reason"] == "tp"
        assert t["risk_money"] == pytest.approx(200.0)  # tick_value_loss 10 per 0.01 per lot in the fake (NOK)
        assert t["context"] is not None and "tf" in t["context"]  # reconstructed from bars before entry
        assert c.put("/api/journal/trades/10", json={"note": "test", "tags": ["x"]}, headers=auth).json()["note"] == "test"
        png = "data:image/png;base64,iVBORw0KGgo="
        shot = c.post("/api/journal/trades/10/screenshot", json={"dataUrl": png}, headers=auth).json()
        name = shot["screenshots"][0]
        assert c.get(f"/api/journal/screenshots/{name}", headers=auth).status_code == 200
        assert c.get("/api/journal/screenshots/..%2F..%2Fauth_token", headers=auth).status_code == 404
        st = c.get("/api/journal/stats", headers=auth).json()
        assert st["summary"]["n"] == 1 and st["summary"]["net"] == pytest.approx(398.6)
        assert c.get("/api/journal/stats").status_code == 401
