"""Event-driven AI commentary.

Loop (every ``poll`` seconds):
1. Diff the latest deterministic analysis into triggers (triggers.py).
2. Queue them; when the cooldown has passed, the feed is live and the budget
   allows the worst-case cost, call Claude once with all pending reasons.
3. Validate the proposed setup with code, store everything in the ledger,
   and publish an ``ai`` message to the panel.

Manual requests ("Spør AI nå") skip the cooldown but never the budget.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import time
from collections import deque
from datetime import datetime
from typing import Any

from ..analysis.engine import ENGINE_VERSION
from ..hub import FeedState, MarketHub
from ..market.models import Timeframe
from .budget import BudgetGuard
from .ledger import Ledger
from .llm import ClaudeCommentator
from .pricing import worst_case_cost_usd
from .prompt import OSLO, PROMPT_VERSION, build_snapshot
from .triggers import Trigger, TriggerDetector
from .validate import validate_setup

log = logging.getLogger(__name__)
PENDING_MAX_AGE_S = 300
EST_INPUT_TOKENS = 3500  # conservative estimate (system prompt + snapshot) for the budget check


class AIService:
    def __init__(
        self,
        hub: MarketHub,
        analysis: Any,  # AnalysisService (has .last)
        ledger: Ledger,
        budget: BudgetGuard,
        commentator: ClaudeCommentator | None,
        usd_nok: float,
        min_interval_s: float = 120.0,
        allow_synthetic: bool = False,
        disabled_reason: str | None = None,
        poll: float = 1.0,
        clock: Any = time.monotonic,
        now: Any = None,
    ) -> None:
        self.hub = hub
        self.analysis = analysis
        self.ledger = ledger
        self.budget = budget
        self.commentator = commentator
        self.usd_nok = usd_nok
        self.min_interval_s = min_interval_s
        self.allow_synthetic = allow_synthetic
        self.disabled_reason = disabled_reason if commentator is None else None
        self.poll = poll
        self._clock = clock
        self._now = now or (lambda: datetime.now(OSLO))
        self.detector = TriggerDetector()
        self.pending: dict[str, tuple[Trigger, float]] = {}
        self._last_call_at: float | None = None
        self._manual = False
        self._busy = False
        self.history: deque[dict[str, Any]] = deque(maxlen=20)
        self.last_status: dict[str, Any] = {}
        self._task: asyncio.Task | None = None
        self.account: Any = None  # AccountMonitor, set by the app (optional)

    # ---- public --------------------------------------------------------------
    def request_manual(self) -> None:
        self._manual = True

    def status_payload(self, note: str | None = None) -> dict[str, Any]:
        st = self.budget.status(self._now())
        if self.disabled_reason:
            state = "disabled"
        elif self._busy:
            state = "thinking"
        else:
            state = "ready"
        cooldown = 0.0
        if self._last_call_at is not None:
            cooldown = max(0.0, self.min_interval_s - (self._clock() - self._last_call_at))
        return {
            "state": state,
            "reason": self.disabled_reason,
            "note": note,
            "model": self.commentator.model if self.commentator else None,
            "pending": [t.reason for t, _ in self.pending.values()],
            "cooldownS": round(cooldown),
            "budget": st.to_wire(self.usd_nok),
        }

    def publish_status(self, note: str | None = None) -> None:
        self.last_status = self.status_payload(note)
        self.hub.publish({"type": "ai_status", "data": self.last_status}, retain=True)

    # ---- loop ----------------------------------------------------------------
    async def step(self) -> None:
        analysis = self.analysis.last
        if analysis is None:
            return
        now_mono = self._clock()
        for trig in self.detector.detect(analysis):
            self.pending[trig.key] = (trig, now_mono)
        for k, (_, at) in list(self.pending.items()):
            if now_mono - at > PENDING_MAX_AGE_S:
                del self.pending[k]

        manual = self._manual
        if not (self.pending or manual):
            return
        if self.disabled_reason or self.commentator is None:
            self._manual = False
            self.publish_status()
            return
        if self.hub.source.is_synthetic and not self.allow_synthetic:
            self._manual = False
            self.publish_status(
                "AI er av for syntetiske demodata (sett COPILOT_AI_ALLOW_DEMO=true for å teste)."
            )
            self.pending.clear()
            return
        if self.hub.stats.state != FeedState.LIVE:
            if manual:
                self._manual = False
                self.publish_status("Ingen ferske priser (markedet stengt?) – AI venter.")
            return
        cooling = self._last_call_at is not None and now_mono - self._last_call_at < self.min_interval_s
        if cooling and not manual:
            return
        await self._call(manual)

    async def _call(self, manual: bool) -> None:
        self._manual = False
        assert self.commentator is not None
        worst = worst_case_cost_usd(self.commentator.model, EST_INPUT_TOKENS, self.commentator.max_tokens)
        blocked = self.budget.check(self._now(), worst)
        if blocked:
            self.pending.clear()
            self.publish_status(blocked)
            return

        triggers = sorted((t for t, _ in self.pending.values()), key=lambda t: -t.priority)
        reasons = [t.reason for t in triggers] or []
        if manual:
            reasons = ["brukeren ba om en oppdatert vurdering"] + reasons
        self.pending.clear()
        hub = self.hub
        tick = hub.stats.last_tick
        now = self._now()
        snapshot = build_snapshot(
            self.analysis.last,
            hub.spec,
            tick,
            hub.candles(Timeframe.M1),
            hub.candles(Timeframe.M5),
            reasons,
            now,
        )
        view = getattr(self.account, "last", None) or {}
        if view.get("available"):
            snapshot["open_positions"] = [
                {
                    "side": "long" if p["type"] == "buy" else "short",
                    "lots": p["volume"],
                    "entry": p["priceOpen"],
                    "sl": p["sl"] or None,
                    "tp": p["tp"] or None,
                    "pnl": round(p["profit"], 2),
                }
                for p in view.get("positions", [])
                if p["symbol"].upper().startswith(("XAU", "GOLD"))
            ]
        self._busy = True
        self._last_call_at = self._clock()
        self.publish_status()
        try:
            res = await self.commentator.comment(snapshot)
        finally:
            self._busy = False
        ts_ms = int(time.time() * 1000)
        call_id = self.ledger.record_call(
            ts_ms=ts_ms,
            model=res.model,
            served_model=res.served_model,
            trigger="manual" if manual else ",".join(t.key for t in triggers)[:500],
            input_tokens=res.input_tokens,
            output_tokens=res.output_tokens,
            cache_read_tokens=res.cache_read_tokens,
            cache_write_tokens=res.cache_write_tokens,
            cost_usd=res.cost_usd,
            ok=int(res.ok),
            error=res.error,
            stop_reason=res.stop_reason,
            request_id=res.request_id,
        )
        if not res.ok:
            self.publish_status(res.error)
            return

        data = res.data or {}
        a1 = (self.analysis.last.get("timeframes") or {}).get("1m") or {}
        checked, rejected = validate_setup(
            data.get("setup") or {},
            tick.bid if tick else None,
            tick.ask if tick else None,
            a1.get("atr"),
            hub.spec.digits if hub.spec else 2,
        )
        msg = {
            "id": call_id,
            "createdAt": ts_ms,
            "tickTime": tick.time_ms if tick else None,
            "price": None if tick is None else {"bid": tick.bid, "ask": tick.ask},
            "atr1m": a1.get("atr"),
            "summary": str(data.get("summary", "")).strip(),
            "bias": data.get("bias", "neutral"),
            "setup": checked,
            "setupRejected": rejected,
            "warnings": [str(w) for w in data.get("warnings", [])][:5],
            "reasons": reasons,
            "manual": manual,
            "model": res.served_model or res.model,
            "costNok": round(res.cost_usd * self.usd_nok, 3),
            "tokens": {"in": res.input_tokens, "out": res.output_tokens},
        }
        self.ledger.record_comment(
            call_id,
            ts_ms,
            hub.symbol,
            tick.bid if tick else None,
            tick.ask if tick else None,
            snapshot,
            {**data, "validated_setup": checked, "rejected": rejected},
            ENGINE_VERSION,
            PROMPT_VERSION,
        )
        self.history.appendleft(msg)
        self.hub.publish({"type": "ai", "data": msg}, retain=True)
        self.publish_status()

    async def run(self) -> None:
        self.publish_status()
        last_status = 0.0
        while True:
            await asyncio.sleep(self.poll)
            try:
                await self.step()
            except Exception:  # noqa: BLE001 - never let AI problems affect the feed
                log.exception("AI step failed")
            if self._clock() - last_status > 15:
                last_status = self._clock()
                self.publish_status(self.last_status.get("note"))

    def start(self) -> None:
        self._task = asyncio.create_task(self.run(), name="ai")

    async def stop(self) -> None:
        if self._task:
            self._task.cancel()
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await self._task
