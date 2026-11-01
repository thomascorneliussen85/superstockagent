"""Personal trading coach.

Learning here means *persistent data and statistics*, not model retraining:
trades, context, AI suggestions and outcomes are stored; patterns are only
reported with minimum samples and confidence intervals; candidate rules must
pass walk-forward testing; drifting setups are flagged; every rule/prompt/
engine version is recorded. Nothing here can change risk limits or trade.
"""

from __future__ import annotations

import asyncio
import contextlib
import hashlib
import json
import logging
import statistics
import time
from datetime import datetime
from typing import Any

from ..analysis.engine import ENGINE_VERSION
from ..journal.context import compact_context
from ..journal.service import JournalService
from ..market.models import Timeframe
from ..sessions import OSLO, session_of
from .ai_eval import HORIZON, TRIGGER_WINDOW, evaluate_setup, summarize_outcomes
from .feedback import match_ai, trade_feedback
from .insights import find_insights, revenge_flags
from .reviews import REVIEW_SCHEMA, REVIEW_SYSTEM, build_review, period_bounds, review_prompt
from .similar import similar_trades
from .store import CoachStore
from .validation import drift, evaluate_candidates

log = logging.getLogger(__name__)
FINAL = {"target", "invalidation", "not_triggered", "ambiguous", "expired"}


class CoachService:
    def __init__(
        self,
        journal: JournalService,
        store: CoachStore,
        ai: Any,
        account: Any,
        analysis: Any,
        max_risk_pct: float,
        min_n: int = 20,
        refresh_s: float = 900.0,
        now: Any = None,
    ) -> None:
        self.journal = journal
        self.store = store
        self.ai = ai
        self.account = account
        self.analysis = analysis
        self.max_risk_pct = max_risk_pct
        self.min_n = min_n
        self.refresh_s = refresh_s
        self._now = now or (lambda: datetime.now(OSLO))
        self.insights: list[dict[str, Any]] = []
        self.drift: list[dict[str, Any]] = []
        self.candidates: list[dict[str, Any]] = []
        self.ai_summary: dict[str, Any] | None = None
        self.last_feedback: dict[str, Any] | None = None
        self.last_refresh_ms: int | None = None
        self._tasks: list[asyncio.Task] = []
        journal.listeners.append(self.on_trade_closed)

    # ---- helpers ------------------------------------------------------------------
    def _balance(self) -> float | None:
        view = getattr(self.account, "last", None) or {}
        return (view.get("account") or {}).get("balance")

    def _comments(self) -> list[dict[str, Any]]:
        ledger = getattr(self.ai, "ledger", None)
        return ledger.comments() if ledger else []

    def record_versions(self, settings: Any) -> None:
        rules = {
            "maxPerTradePct": settings.risk_max_per_trade_pct,
            "dailyLossLimitPct": settings.risk_daily_loss_limit_pct,
            "nearSlFraction": settings.risk_near_sl_fraction,
        }
        h = hashlib.sha256(json.dumps(rules, sort_keys=True).encode()).hexdigest()[:10]
        self.store.record_version("risk_rules", h, rules)
        self.store.record_version("analysis_engine", ENGINE_VERSION, {})
        c = getattr(self.ai, "commentator", None)
        if c is not None:
            self.store.record_version("ai_prompt", c.prompt_version, {"model": c.model, "effort": c.effort})

    # ---- after each closed trade ------------------------------------------------------
    def on_trade_closed(self, trade: dict[str, Any]) -> dict[str, Any]:
        trades = self.journal.store.trades()
        rev = revenge_flags(trades)
        durations = [(t["close_ms"] - t["open_ms"]) / 60000 for t in trades if t.get("close_ms")]
        typical = statistics.median(durations) if durations else None
        link = match_ai(trade, self._comments())
        fb = trade_feedback(
            trade,
            self.insights,
            bool(rev.get(trade["position_id"])),
            link,
            self._balance(),
            self.max_risk_pct,
            typical,
        )
        fb.update(
            {
                "position_id": trade["position_id"],
                "direction": trade["direction"],
                "closeMs": trade["close_ms"],
                "net": trade["net"],
                "r": trade.get("r_multiple"),
            }
        )
        self.journal.store.set_eval(trade["position_id"], "feedback", fb)
        self.journal.store.set_eval(trade["position_id"], "ai_link", link)
        self.last_feedback = fb
        self.journal.hub.publish({"type": "trade_feedback", "data": fb}, retain=True)
        self.publish()
        return fb

    # ---- periodic analysis ----------------------------------------------------------
    def refresh_sync(self) -> None:
        trades = self.journal.store.trades()
        self.insights = find_insights(trades, self.min_n)
        self.store.update_knowledge(self.insights)
        self.drift = drift(trades)
        self.candidates = evaluate_candidates(trades)
        self.last_refresh_ms = int(time.time() * 1000)

    async def evaluate_ai(self) -> None:
        src = self.journal.hub.source
        if not hasattr(src, "rates_range") or self.journal.hub.spec is None:
            self.ai_summary = summarize_outcomes(self._ai_rows())
            return
        done = self.store.outcomes()
        now_ms = int(time.time() * 1000)
        for c in self._comments():
            if not c.get("setup") or (done.get(c["id"], {}).get("status") in FINAL):
                continue
            if now_ms - c["ts_ms"] < TRIGGER_WINDOW * 60_000:
                continue
            end = min(now_ms, c["ts_ms"] + (TRIGGER_WINDOW + HORIZON + 1) * 60_000)
            try:
                bars = await src.rates_range(self.journal.hub.spec.symbol, Timeframe.M1, c["ts_ms"], end)
            except Exception:  # noqa: BLE001
                continue
            res = evaluate_setup(c["setup"], c["ts_ms"], bars, now_ms)
            self.store.set_outcome(c["id"], res)
        self.ai_summary = summarize_outcomes(self._ai_rows())

    def _ai_rows(self) -> list[dict[str, Any]]:
        outcomes = self.store.outcomes()
        trades = self.journal.store.trades()
        rows = []
        for c in self._comments():
            if not c.get("setup") or c["id"] not in outcomes:
                continue
            o = outcomes[c["id"]]
            follow = "ignored"
            for t in trades:
                if 0 <= t["open_ms"] - c["ts_ms"] <= 15 * 60_000:
                    st = match_ai(t, [c])["status"]
                    follow = {"followed": "followed", "contrary": "contrary"}.get(st, follow)
            rows.append(
                {
                    "status": o["status"],
                    "r": o.get("r"),
                    "direction": c["setup"]["direction"],
                    "kind": c["setup"].get("kind"),
                    "promptVersion": c.get("promptVersion"),
                    "link": follow,
                }
            )
        return rows

    def similar_now(self) -> dict[str, Any]:
        a = self.analysis.last
        if not a:
            return {}
        ctx = compact_context(a)
        sess = session_of(int(time.time() * 1000))
        trades = self.journal.store.trades()
        return {d: similar_trades(ctx, sess, trades, d) for d in ("long", "short")}

    # ---- reviews ---------------------------------------------------------------------------
    async def generate_review(
        self, period: str, now: datetime | None = None, use_ai: bool = True
    ) -> dict[str, Any]:
        now = now or self._now()
        start, end, label = period_bounds(period, now)
        all_trades = self.journal.store.trades()
        trades = [t for t in all_trades if start <= (t["close_ms"] or 0) < end]
        review = build_review(
            period,
            label,
            trades,
            all_trades,
            self.insights,
            self.ai_summary,
            self.max_risk_pct,
            self._balance(),
        )
        review["narrative"] = None
        if use_ai and trades and self.ai is not None:
            data, err = await self.ai.generate_text(
                REVIEW_SYSTEM, review_prompt(review), REVIEW_SCHEMA, f"review:{period}"
            )
            review["narrative"] = data
            review["narrativeError"] = err
        self.store.save_review(period, start, end, review)
        self.publish()
        return review

    async def _maybe_auto_review(self) -> None:
        now = self._now()
        if now.weekday() < 5 and (now.hour, now.minute) >= (22, 30):
            start, end, _ = period_bounds("day", now)
            if not self.store.has_review("day", start):
                trades = [t for t in self.journal.store.trades() if start <= (t["close_ms"] or 0) < end]
                if trades:
                    await self.generate_review("day", now)
        if now.weekday() == 5:  # Saturday: review the week that just ended
            from datetime import timedelta

            prev = now - timedelta(days=1)
            start, _, _ = period_bounds("week", prev)
            if not self.store.has_review("week", start):
                await self.generate_review("week", prev)

    # ---- publishing ---------------------------------------------------------------------
    def summary(self) -> dict[str, Any]:
        return {
            "minSample": self.min_n,
            "lastRefreshMs": self.last_refresh_ms,
            "insights": self.insights,
            "knowledge": self.store.knowledge(),
            "drift": self.drift,
            "candidates": self.candidates,
            "ai": self.ai_summary,
            "versions": self.store.versions(),
            "lastFeedback": self.last_feedback,
            "trades": len(self.journal.store.trades()),
        }

    def publish(self) -> None:
        panel = {
            "minSample": self.min_n,
            "trades": len(self.journal.store.trades()),
            "insights": self.insights[:5],
            "drift": [d for d in self.drift if d["status"] == "worse"],
            "recommended": [c for c in self.candidates if c.get("recommended")],
            "lastFeedback": self.last_feedback,
            "similar": self.similar_now(),
            "reviews": [
                {"id": r["id"], "period": r["period"], "label": r["label"]} for r in self.store.reviews(3)
            ],
        }
        self.journal.hub.publish({"type": "coach", "data": panel}, retain=True)

    async def run(self) -> None:
        await asyncio.sleep(8)
        last_full = 0.0
        while True:
            try:
                if time.monotonic() - last_full > self.refresh_s:
                    await asyncio.to_thread(self.refresh_sync)
                    await self.evaluate_ai()
                    last_full = time.monotonic()
                await self._maybe_auto_review()
                self.publish()
            except Exception:  # noqa: BLE001
                log.exception("Coach step failed")
            await asyncio.sleep(60)

    def start(self) -> None:
        self._tasks.append(asyncio.create_task(self.run(), name="coach"))

    async def stop(self) -> None:
        for t in self._tasks:
            t.cancel()
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await t
