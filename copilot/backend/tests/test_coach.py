import asyncio
import random
from datetime import datetime

import pytest

from app.coach.ai_eval import evaluate_setup, summarize_outcomes
from app.coach.feedback import match_ai, trade_feedback
from app.coach.insights import find_insights, revenge_flags
from app.coach.reviews import build_review, period_bounds
from app.coach.similar import similar_trades
from app.coach.store import CoachStore
from app.coach.validation import drift, walk_forward
from app.journal.store import JournalStore
from app.market.models import Candle, Timeframe
from app.sessions import OSLO

T0 = 1_790_000_000_000  # a Tuesday-ish base; hours vary below
HOUR = 3_600_000


def make_trades(n=200, seed=1, london_edge=0.8, against_penalty=-0.6, drift_last=0):
    rng = random.Random(seed)
    out = []
    for i in range(n):
        utc_h = rng.choice([3, 9, 10, 13, 17, 18])  # Asia / London / overlap / NY
        open_ms = T0 + i * 6 * HOUR + utc_h * HOUR
        session = {3: "Asia", 9: "London", 10: "London", 13: "London/NY", 17: "New York", 18: "New York"}[utc_h]
        with15 = rng.choice(["with", "against"])
        r = rng.gauss(0.1, 1.0)
        if session == "London":
            r += london_edge
        if with15 == "against":
            r += against_penalty
        if drift_last and i >= n - drift_last:
            r -= 2.0
        direction = rng.choice(["long", "short"])
        ctx = {"tf": {"1m": {"score": 2, "rsi": 55, "atrPct": 50, "volatility": "normal"},
                      "5m": {"score": 2, "rsi": 55, "distEma20Atr": 0.2}, "15m": {"score": 3}, "1h": {"score": 1}},
               "with15m": with15}
        out.append({"position_id": i + 1, "symbol": "XAUUSD", "direction": direction, "open_ms": open_ms,
                    "close_ms": open_ms + 10 * 60_000, "volume": 0.1, "entry_price": 4000.0, "exit_price": 4001.0,
                    "sl": 3998.0, "tp": 4004.0, "gross": r * 20, "commission": -0.7, "swap": 0.0, "fee": 0.0,
                    "net": round(r * 20, 2), "risk_money": 20.0, "r_multiple": round(r, 3),
                    "exit_reason": rng.choice(["tp", "sl", "manual"]), "closed": 1, "session": session, "deals": 2,
                    "setup": "pullback" if i % 3 else "breakout", "context": ctx, "note": "", "tags": []})
    return out


def test_insights_find_real_effects_and_respect_min_sample():
    ins = find_insights(make_trades(), min_n=20)
    ids = {i["id"]: i for i in ins}
    assert "session:London" in ids and ids["session:London"]["kind"] == "strength"
    assert "with:15m" in ids and ids["with:15m"]["diff"] > 0  # better with the 15m trend
    lo, hi = ids["with:15m"]["ci"]
    assert lo > 0 and hi > lo
    # With too few trades, nothing is claimed
    assert [i for i in find_insights(make_trades(n=30), min_n=20) if "kind" in i and i["kind"] != "habit"] == []


def test_insights_no_effect_mostly_silent():
    trades = make_trades(n=200, seed=3, london_edge=0.0, against_penalty=0.0)
    ins = [i for i in find_insights(trades, min_n=20) if i["kind"] != "habit"]
    assert len(ins) <= 2  # few false positives at 95 % with ~40 splits


def test_revenge_and_feedback():
    trades = make_trades(n=3)
    trades[0]["net"] = -20.0
    trades[1]["open_ms"] = trades[0]["close_ms"] + 60_000
    rev = revenge_flags(trades)
    assert rev[2] is True and rev[1] is False
    t = {**trades[1], "net": 15.0, "r_multiple": 0.75, "exit_reason": "manual", "tp": 4004.0,
         "entry_price": 4000.0, "exit_price": 4001.0, "context": {"with15m": "against"}}
    fb = trade_feedback(t, [{"id": "with:15m", "diff": 0.6, "kind": "strength"}], True,
                        {"status": "followed"}, 1000.0, 1.0, 10.0)
    texts = " ".join(p["text"] for p in fb["points"])
    assert fb["headline"].startswith("Gevinst: +15,00 (+0,75 R)")
    assert "2,0 % av kontoen" in texts  # 20/1000 over 1 % rule
    assert "mot 15m-trenden" in texts and "før take-profit" in texts and "etter et tap" in texts
    assert "fulgte AI-forslaget" in texts


def test_match_ai():
    t = {"open_ms": 1_000_000, "direction": "long", "entry_price": 4000.2}
    c = {"id": 1, "ts_ms": 1_000_000 - 60_000,
         "setup": {"direction": "long", "entryLow": 3999.8, "entryHigh": 4000.0}}
    assert match_ai(t, [c])["status"] == "followed"
    assert match_ai({**t, "direction": "short"}, [c])["status"] == "contrary"
    assert match_ai(t, [{**c, "ts_ms": 0}])["status"] == "none"


def test_similar_trades():
    trades = make_trades()
    ctx = trades[0]["context"]
    res = similar_trades(ctx, "London", trades, "long", k=15)
    assert res["n"] == 15 and res["enough"] and res["winRateCi"][0] <= res["winRate"] <= res["winRateCi"][1]
    assert similar_trades({}, "London", trades, "long")["n"] == 0


def bar(i, lo, hi, base=1_000_000):
    return Candle("XAUUSD", Timeframe.M1, base + i * 60_000, (lo + hi) / 2, hi, lo, (lo + hi) / 2, closed=True)


SETUP = {"direction": "long", "entryLow": 3999.5, "entryHigh": 4000.0, "invalidation": 3998.0, "target": 4004.0,
         "rr": 1.8, "spreadAtCheck": 0.2}


def test_ai_setup_evaluation():
    now = 1_000_000 + 400 * 60_000
    hit = [bar(0, 4000.5, 4001), bar(1, 3999.8, 4000.6), bar(2, 4001, 4004.5)]
    assert evaluate_setup(SETUP, 1_000_000, hit, now)["status"] == "target"
    stop = [bar(0, 3999.8, 4000.2), bar(1, 3997.5, 3999.9)]
    assert evaluate_setup(SETUP, 1_000_000, stop, now) == {"status": "invalidation", "r": -1.0,
                                                           "triggeredAt": 1_000_000, "resolvedAt": 1_060_000}
    both = [bar(0, 3997.0, 4005.0)]
    assert evaluate_setup(SETUP, 1_000_000, both, now)["status"] == "ambiguous"
    never = [bar(i, 4002, 4003) for i in range(40)]
    assert evaluate_setup(SETUP, 1_000_000, never, now)["status"] == "not_triggered"
    assert evaluate_setup(SETUP, 1_000_000, never[:5], 1_000_000 + 5 * 60_000)["status"] == "pending"
    s = summarize_outcomes([{"status": "target", "r": 1.8, "direction": "long", "kind": "pullback",
                             "promptVersion": "3.1.0", "link": "followed"},
                            {"status": "invalidation", "r": -1.0, "direction": "long", "kind": "pullback",
                             "promptVersion": "3.1.0", "link": "ignored"}])
    assert s["all"]["hitRate"] == 0.5 and s["all"]["meanR"] == pytest.approx(0.4)
    assert set(s["byFollow"]) == {"followed", "ignored"} and "forårsaket" in s["note"]


def test_walk_forward_and_drift():
    trades = make_trades(n=300, seed=5, london_edge=0.0, against_penalty=-1.2)
    good = walk_forward(trades, lambda t: (t.get("context") or {}).get("with15m") == "with")
    assert good["recommended"] and good["oosCi"][0] > 0
    rng = random.Random(9)
    coin = {t["position_id"]: rng.random() < 0.5 for t in trades}
    bad = walk_forward(trades, lambda t: coin[t["position_id"]])
    assert not bad["recommended"]
    assert walk_forward(trades[:20], lambda t: True)["recommended"] is False
    d = {x["group"]: x for x in drift(make_trades(n=120, seed=2, drift_last=20))}
    assert d["(alle handler)"]["status"] == "worse"


def test_knowledge_and_versions(tmp_path):
    js = JournalStore(tmp_path / "c.db")
    cs = CoachStore(js)
    ins = [{"id": "session:London", "kind": "strength", "title": "A", "detail": "d", "strength": "solid"}]
    cs.update_knowledge(ins, now_ms=1_000)
    cs.update_knowledge(ins, now_ms=2_000)
    k = cs.knowledge()[0]
    assert k["timesConfirmed"] == 2 and k["status"] == "active"
    cs.update_knowledge([], now_ms=2_000 + 31 * 86_400_000)
    assert cs.knowledge()[0]["status"] == "stale"
    cs.record_version("ai_prompt", "3.1.0", {"model": "m"})
    cs.record_version("ai_prompt", "3.1.0", {"model": "m"})
    assert len(cs.versions()) == 1


def test_review_build_and_bounds():
    now = datetime(2026, 11, 4, 23, 0, tzinfo=OSLO)  # Wednesday
    s, e, label = period_bounds("week", now)
    assert datetime.fromtimestamp(s / 1000, OSLO).weekday() == 0 and (e - s) == 7 * 86_400_000
    assert period_bounds("day", now)[2] == "04.11.2026"
    trades = make_trades(n=10)
    trades[0]["sl"] = None
    r = build_review("day", "x", trades, trades, [], None, 1.0, 1000.0)
    assert r["adherence"]["withSl"] == 9 and r["adherence"]["overRiskRule"] == 10
    assert any("manglet stop-loss" in s for s in r["suggestions"])


def test_coach_service_feedback_and_review(tmp_path):
    from app.coach.service import CoachService
    from app.hub import MarketHub
    from app.journal.service import JournalService
    from app.market.demo import DemoMarketSource

    class FakeAI:
        ledger = None

        async def generate_text(self, system, user, schema, trigger, max_tokens=3000):
            assert "Fakta for perioden" in user
            return {"summary": "Bra dag.", "went_well": ["a"], "improve": ["b"], "focus_next": "c"}, None

    class Acc:
        last = {"account": {"balance": 1000.0}}

    class An:
        last = None

    hub = MarketHub(DemoMarketSource(seed=1, realtime=False), "XAUUSD", "demo")
    js = JournalStore(tmp_path / "x.db")
    journal = JournalService(hub, js)
    coach = CoachService(journal, CoachStore(js), FakeAI(), Acc(), An(), 1.0, min_n=20)
    sub = hub.subscribe()
    trades = make_trades(n=5)
    js.replace_trades([{k: t[k] for k in ("position_id", "symbol", "direction", "open_ms", "close_ms", "volume",
                                         "entry_price", "exit_price", "sl", "tp", "gross", "commission", "swap",
                                         "fee", "net", "risk_money", "r_multiple", "exit_reason", "closed",
                                         "session", "deals")} for t in trades])
    fb = coach.on_trade_closed(js.trade(1))
    assert fb["position_id"] == 1 and js.evals("feedback")[1]["headline"] == fb["headline"]
    types = [sub.queue.get_nowait()["type"] for _ in range(sub.queue.qsize())]
    assert "trade_feedback" in types and "coach" in types
    now = datetime.fromtimestamp(trades[0]["close_ms"] / 1000, OSLO)
    review = asyncio.run(coach.generate_review("day", now))
    assert review["narrative"]["summary"] == "Bra dag." and coach.store.reviews()[0]["period"] == "day"
