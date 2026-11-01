import asyncio
import json
from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

from app.ai.budget import BudgetGuard, weekdays_left
from app.ai.ledger import Ledger
from app.ai.llm import ClaudeCommentator, LlmResult
from app.ai.pricing import cost_usd, price_for, worst_case_cost_usd
from app.ai.prompt import OUTPUT_SCHEMA, build_snapshot, trading_session
from app.ai.service import AIService
from app.ai.triggers import TriggerDetector
from app.ai.validate import risk_reward, validate_setup
from app.hub import FeedState, MarketHub
from app.market.demo import DEMO_SPEC, DemoMarketSource
from app.market.models import Tick, Timeframe

OSLO = ZoneInfo("Europe/Oslo")
WED = datetime(2026, 11, 4, 10, 0, tzinfo=OSLO)  # a Wednesday


# ---- pricing & budget --------------------------------------------------------
def test_pricing():
    assert cost_usd("claude-opus-5-5", 1_000_000, 0) == pytest.approx(4.0)
    assert cost_usd("claude-opus-5-5", 0, 1_000_000) == pytest.approx(20.0)
    assert price_for("claude-haiku-5-5").output == 0.5
    assert price_for("some-future-model").output == 50.0  # unknown -> most expensive (safe)
    assert worst_case_cost_usd("claude-opus-5-5", 3500, 2500) == pytest.approx(0.064)


def test_weekdays_left():
    assert weekdays_left(datetime(2026, 11, 30, tzinfo=OSLO)) == 1  # Monday, last day
    assert weekdays_left(datetime(2026, 11, 29, tzinfo=OSLO)) == 1  # Sunday -> only Monday 30th


def test_budget_caps_month_and_paces_days():
    led = Ledger(":memory:")
    g = BudgetGuard(led, monthly_budget_nok=50, usd_nok=10.0)  # $5/month
    st = g.status(WED)
    assert st.monthly_cap_usd == 5.0 and st.month_spent_usd == 0
    # 19 weekdays left from Wed 4 Nov to Mon 30 Nov -> ~0.263 USD/day
    assert st.day_allowance_usd == pytest.approx(5.0 / 19)
    assert g.check(WED, 0.05) is None
    ts = int(WED.timestamp() * 1000)
    led.record_call(ts_ms=ts, model="m", trigger="t", cost_usd=0.25, ok=1)
    assert "Dagens" in g.check(WED, 0.05)
    # Next day the allowance recovers
    thu = WED.replace(day=5)
    assert g.check(thu, 0.05) is None
    led.record_call(ts_ms=ts, model="m", trigger="t", cost_usd=4.8, ok=1)
    assert "Månedsbudsjettet" in g.check(thu, 0.05)
    assert g.status(thu).to_wire(10.0)["monthSpentNok"] == pytest.approx(50.5)


# ---- validation --------------------------------------------------------------
def test_risk_reward_includes_spread():
    assert risk_reward("long", 100, 98, 104, 0) == pytest.approx(2.0)
    assert risk_reward("long", 100, 98, 104, 0.2) == pytest.approx(3.8 / 2.2)
    assert risk_reward("short", 100, 102, 96, 0.2) == pytest.approx(3.8 / 2.2)


def setup(direction="long", lo=3999.5, hi=4000.0, inv=3997.0, tgt=4005.0):
    return {"direction": direction, "kind": "pullback", "entry_low": lo, "entry_high": hi,
            "invalidation": inv, "target": tgt, "supporting": ["a"], "conflicting": []}


def test_validate_setup():
    ok, why = validate_setup(setup(), 4000.0, 4000.2, 1.5)
    assert why is None and ok["rr"] > 1 and ok["entryLow"] == 3999.5
    assert validate_setup(setup(inv=4001), 4000.0, 4000.2, 1.5)[0] is None  # invalidation above entry
    bad, why = validate_setup(setup("short", inv=3990, tgt=4010), 4000.0, 4000.2, 1.5)
    assert bad is None and "short" in why
    far, why = validate_setup(setup(lo=3950, hi=3951, inv=3948, tgt=3960), 4000.0, 4000.2, 1.5)
    assert far is None and "langt" in why
    none, why = validate_setup({"direction": "none"}, 4000.0, 4000.2, 1.5)
    assert none is None and why is None


# ---- triggers ----------------------------------------------------------------
def analysis(trend5="up", events=(), spread_state="normal", rsi_zone="neutral", price=4000.0, levels=None):
    tf = lambda label: {"insufficient": False, "trend": {"label": label}, "rsiZone": rsi_zone, "rsi": 50,  # noqa: E731
                        "atr": 2.0, "levels": levels or {"support": [], "resistance": []}}
    return {"price": {"bid": price}, "timeframes": {"1m": tf("up"), "5m": tf(trend5), "15m": tf("up"), "1h": tf("up")},
            "recentEvents": list(events), "spread": {"state": spread_state, "current": 0.6}}


def test_triggers_baseline_then_changes():
    d = TriggerDetector()
    ev = {"tf": "5m", "type": "bos_up", "t": 1, "level": 4001.0}
    assert d.detect(analysis(events=[ev])) == []  # first call = baseline, history not replayed
    assert d.detect(analysis(events=[ev])) == []
    t = d.detect(analysis(trend5="down", events=[ev, {**ev, "t": 2, "type": "breakout_down"}]))
    keys = {x.key.split(":")[0] for x in t}
    assert keys == {"ev", "trend"}
    assert d.detect(analysis(trend5="down")) == []  # no repeat
    sp = d.detect(analysis(trend5="down", spread_state="high"))
    assert [x.key for x in sp] == ["spread:high"]
    lv = {"support": [{"price": 3999.8, "touches": 3}], "resistance": []}
    near = d.detect(analysis(trend5="down", spread_state="high", levels=lv))
    assert near and near[0].key.startswith("level:")


# ---- prompt ------------------------------------------------------------------
def test_snapshot_is_compact_and_schema_strict():
    async def hist():
        src = DemoMarketSource(seed=2, realtime=False)
        return {tf: await src.history("XAUUSD", tf, 300) for tf in Timeframe}

    from app.analysis.engine import analyze

    c = asyncio.run(hist())
    tick = Tick("XAUUSD", 0, 4000.0, 4000.2)
    a = analyze(c, DEMO_SPEC, tick, [0.2] * 100, 0)
    a["recentEvents"] = []
    snap = build_snapshot(a, DEMO_SPEC, tick, c[Timeframe.M1], c[Timeframe.M5], ["test"], WED)
    text = json.dumps(snap, separators=(",", ":"))
    assert len(text) < 6000  # ~1.5k tokens: keeps each call cheap
    assert snap["session"] == "London" and snap["update_reasons"] == ["test"]
    assert OUTPUT_SCHEMA["additionalProperties"] is False
    assert OUTPUT_SCHEMA["properties"]["setup"]["additionalProperties"] is False
    assert trading_session(datetime(2026, 11, 4, 14, tzinfo=OSLO)) == "London/New York overlap"


# ---- LLM wrapper against the real SDK request path (mocked HTTP) --------------
def test_llm_request_through_real_sdk(monkeypatch):
    import anthropic
    import httpx2

    seen = {}
    body = {"summary": "Gull er i en opptrend.", "bias": "long", "warnings": [],
            "setup": {"direction": "none", "kind": "none", "entry_low": 0, "entry_high": 0,
                      "invalidation": 0, "target": 0, "supporting": [], "conflicting": []}}

    def handler(request):
        seen["headers"] = dict(request.headers)
        seen["json"] = json.loads(request.content)
        return httpx2.Response(200, json={
            "id": "msg_1", "type": "message", "role": "assistant", "model": "claude-opus-5-5",
            "content": [{"type": "text", "text": json.dumps(body)}], "stop_reason": "end_turn",
            "stop_sequence": None, "usage": {"input_tokens": 1500, "output_tokens": 400},
        })

    client = anthropic.AsyncAnthropic(
        api_key="test", http_client=anthropic.DefaultAsyncHttpxClient(transport=httpx2.MockTransport(handler))
    )
    c = ClaudeCommentator("test", "claude-opus-5-5", "low", 2500, True, client=client)
    res = asyncio.run(c.comment({"x": 1}))
    assert res.ok and res.data["bias"] == "long"
    assert res.cost_usd == pytest.approx((1500 * 4 + 400 * 20) / 1e6)
    sent = seen["json"]
    assert sent["model"] == "claude-opus-5-5" and sent["fallbacks"] == "default"
    assert sent["output_config"]["format"]["type"] == "json_schema"
    assert sent["output_config"]["effort"] == "low"
    assert "server-side-fallback-2026-07-01" in seen["headers"]["anthropic-beta"]
    assert "thinking" not in sent and "temperature" not in sent


def test_llm_refusal_and_auth_error():
    import anthropic
    import httpx2

    def refuse(request):
        return httpx2.Response(200, json={
            "id": "m", "type": "message", "role": "assistant", "model": "claude-opus-5-5", "content": [],
            "stop_reason": "refusal", "stop_sequence": None, "usage": {"input_tokens": 10, "output_tokens": 0}})

    def unauthorized(request):
        return httpx2.Response(401, json={"type": "error", "error": {"type": "authentication_error", "message": "x"}})

    for handler, needle in ((refuse, "avslo"), (unauthorized, "API-nøkkel")):
        client = anthropic.AsyncAnthropic(
            api_key="t", max_retries=0,
            http_client=anthropic.DefaultAsyncHttpxClient(transport=httpx2.MockTransport(handler)))
        res = asyncio.run(ClaudeCommentator("t", "claude-opus-5-5", client=client).comment({}))
        assert not res.ok and needle in res.error


# ---- service end to end --------------------------------------------------------
class FakeCommentator:
    model = "claude-opus-5-5"
    max_tokens = 2500

    def __init__(self, data):
        self.data = data
        self.calls = []

    async def comment(self, snapshot):
        self.calls.append(snapshot)
        return LlmResult(self.data, self.model, served_model=self.model, input_tokens=1500, output_tokens=400,
                         cost_usd=0.014, stop_reason="end_turn")


class Clock:
    def __init__(self):
        self.t = 1000.0

    def __call__(self):
        return self.t


def make_service(data, allow_synthetic=True, budget_nok=50):
    async def build():
        src = DemoMarketSource(seed=4, realtime=False)
        hub = MarketHub(src, "XAUUSD", "demo")
        hub.spec = DEMO_SPEC
        for tf in Timeframe:
            hub.seed_history(tf, await src.history("XAUUSD", tf, 300))
        return hub

    hub = asyncio.run(build())
    hub.ingest(Tick("XAUUSD", int(datetime.now().timestamp() * 1000), 4000.0, 4000.2))
    from app.analysis.service import AnalysisService

    an = AnalysisService(hub)
    an.compute()
    led = Ledger(":memory:")
    clock = Clock()
    fake = FakeCommentator(data)
    svc = AIService(hub, an, led, BudgetGuard(led, budget_nok, 10.0), fake, usd_nok=10.0, min_interval_s=120,
                    allow_synthetic=allow_synthetic, clock=clock, now=lambda: WED)
    return svc, hub, an, fake, clock, led


GOOD = {"summary": "Mulig long.", "bias": "long", "warnings": ["Høy spread"],
        "setup": setup(lo=3999.6, hi=4000.0, inv=3997.5, tgt=4004.0)}


def test_service_manual_call_publishes_validated_comment():
    svc, hub, an, fake, clock, led = make_service(GOOD)
    sub = hub.subscribe()
    asyncio.run(svc.step())  # baseline, nothing pending
    assert fake.calls == []
    svc.request_manual()
    asyncio.run(svc.step())
    assert len(fake.calls) == 1
    assert fake.calls[0]["update_reasons"][0].startswith("brukeren")
    msgs = []
    while not sub.queue.empty():
        msgs.append(sub.queue.get_nowait())
    ai = [m for m in msgs if m["type"] == "ai"][-1]["data"]
    assert ai["setup"]["direction"] == "long" and ai["setup"]["rr"] > 1
    assert ai["costNok"] == pytest.approx(0.14)
    status = [m for m in msgs if m["type"] == "ai_status"][-1]["data"]
    assert status["budget"]["monthSpentNok"] == pytest.approx(0.14)
    assert led.calls_since(0) == 1


def test_service_cooldown_and_budget_and_demo_guard():
    svc, hub, an, fake, clock, led = make_service(GOOD)
    asyncio.run(svc.step())
    from app.ai.triggers import Trigger

    svc.pending["x"] = (Trigger("x", "test", 1), clock.t)
    asyncio.run(svc.step())
    assert len(fake.calls) == 1
    svc.pending["y"] = (Trigger("y", "test2", 1), clock.t)
    clock.t += 30
    asyncio.run(svc.step())
    assert len(fake.calls) == 1  # cooling down
    clock.t += 120
    asyncio.run(svc.step())
    assert len(fake.calls) == 2

    svc2, *_ , fake2, _, _ = make_service(GOOD, budget_nok=0.1)
    svc2.request_manual()
    asyncio.run(svc2.step())
    assert fake2.calls == [] and "budsjett" in svc2.last_status["note"].lower()

    svc3, *_ , fake3, _, _ = make_service(GOOD, allow_synthetic=False)
    svc3.request_manual()
    asyncio.run(svc3.step())
    assert fake3.calls == [] and "demodata" in svc3.last_status["note"]


def test_service_rejects_invalid_setup_but_keeps_comment():
    bad = {**GOOD, "setup": setup(inv=4003.0)}
    svc, hub, *_ = make_service(bad)
    svc.request_manual()
    asyncio.run(svc.step())
    ai = svc.history[0]
    assert ai["setup"] is None and "long" in ai["setupRejected"]
    assert ai["summary"] == "Mulig long."


def test_service_waits_when_market_closed():
    svc, hub, an, fake, clock, led = make_service(GOOD)
    hub.stats.state = FeedState.STALE
    svc.request_manual()
    asyncio.run(svc.step())
    assert fake.calls == [] and "stengt" in svc.last_status["note"]
