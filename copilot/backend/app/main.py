"""FastAPI application factory and entry point.

Run with::

    python -m app            # from copilot/backend
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from . import __version__
from .account.monitor import AccountMonitor
from .account.risk import RiskRules
from .ai.budget import BudgetGuard
from .ai.ledger import Ledger
from .ai.llm import ClaudeCommentator
from .ai.service import AIService
from .analysis.service import AnalysisService
from .api import routes, ws
from .config import Settings, TradingMode, get_settings
from .hub import MarketHub
from .market.demo import DemoMarketSource
from .market.mt5_source import Mt5MarketSource
from .market.source import MarketDataSource
from .security import OriginPolicy, load_or_create_token

log = logging.getLogger("copilot")


def build_source(settings: Settings) -> MarketDataSource:
    if settings.mode is TradingMode.DEMO:
        return DemoMarketSource(start_price=settings.demo_start_price, seed=settings.demo_seed)
    return Mt5MarketSource(
        expected_mode=settings.mode.value,
        broker_symbol=settings.mt5_symbol,
        terminal_path=settings.mt5_path,
        utc_offset_minutes=settings.mt5_utc_offset_minutes,
        data_dir=settings.data_dir,
        poll_interval=settings.mt5_poll_interval_seconds,
    )


def build_ai(settings: Settings, hub: MarketHub, analysis: AnalysisService) -> AIService:
    ledger = Ledger(settings.data_dir / "copilot.db")
    budget = BudgetGuard(ledger, settings.ai_monthly_budget_nok, settings.ai_usd_nok)
    commentator = None
    reason = None
    if not settings.ai_enabled:
        reason = "AI er slått av (COPILOT_AI_ENABLED=false)."
    elif settings.anthropic_api_key is None or not settings.anthropic_api_key.get_secret_value().strip():
        reason = "Mangler Anthropic API-nøkkel. Legg ANTHROPIC_API_KEY=... i .env og start backend på nytt."
    else:
        commentator = ClaudeCommentator(
            settings.anthropic_api_key.get_secret_value().strip(),
            settings.ai_model,
            settings.ai_effort,
            settings.ai_max_tokens,
            settings.ai_fallbacks,
        )
    return AIService(
        hub,
        analysis,
        ledger,
        budget,
        commentator,
        usd_nok=settings.ai_usd_nok,
        min_interval_s=settings.ai_min_interval_seconds,
        allow_synthetic=settings.ai_allow_demo,
        disabled_reason=reason,
    )


def create_app(settings: Settings | None = None, source: MarketDataSource | None = None) -> FastAPI:
    settings = settings or get_settings()
    policy = OriginPolicy(settings)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        app.state.token = load_or_create_token(settings)
        hub = MarketHub(
            source or build_source(settings),
            settings.symbol,
            settings.mode.value,
            stale_after_seconds=settings.stale_after_seconds,
        )
        app.state.hub = hub
        analysis = AnalysisService(hub, interval=settings.analysis_interval_seconds)
        app.state.analysis = analysis
        app.state.ai = build_ai(settings, hub, analysis)
        rules = RiskRules(
            settings.risk_max_per_trade_pct,
            settings.risk_daily_loss_limit_pct,
            settings.risk_near_sl_fraction,
            settings.risk_min_margin_level_pct,
        )
        app.state.account = AccountMonitor(hub, analysis, rules)
        app.state.ai.account = app.state.account
        await hub.start()
        analysis.start()
        app.state.ai.start()
        app.state.account.start()
        log.info(
            "AI Trading Copilot backend %s started (mode=%s, read-only)", __version__, settings.mode.value
        )
        try:
            yield
        finally:
            await app.state.account.stop()
            await app.state.ai.stop()
            app.state.ai.ledger.close()
            await analysis.stop()
            await hub.stop()

    app = FastAPI(title="AI Trading Copilot", version=__version__, lifespan=lifespan)
    app.state.settings = settings
    app.state.origin_policy = policy
    app.add_middleware(
        CORSMiddleware,
        allow_origins=policy.cors_origins,
        allow_origin_regex=policy.cors_origin_regex,
        allow_methods=["GET", "POST"],
        allow_headers=["Authorization", "Content-Type"],
    )
    app.include_router(routes.router)
    app.include_router(ws.router)
    return app


def port_in_use_message(host: str, port: int) -> str | None:
    """Explains (in Norwegian) why the port is busy, or None if it is free."""
    import socket
    import urllib.request

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        try:
            s.bind((host, port))
            return None
        except OSError:
            pass
    try:
        with urllib.request.urlopen(f"http://{host}:{port}/api/health", timeout=2) as r:
            ours = b"version" in r.read()
    except Exception:  # noqa: BLE001
        ours = False
    if ours:
        return (
            f"En AI Copilot-backend kjorer allerede paa port {port} (sannsynligvis et annet svart vindu).\n"
            "  Lukk det andre vinduet og start paa nytt - eller bruk det som allerede kjorer."
        )
    return (
        f"Port {port} brukes allerede av et annet program.\n"
        "  Lukk programmet, eller velg en annen port med COPILOT_PORT=8766 i .env\n"
        "  (og endre adressen i utvidelsens innstillinger tilsvarende)."
    )


def ai_key_diagnosis(settings: Settings) -> list[str]:
    """Plain-language hints for why no Anthropic API key was found (ASCII only for cmd.exe)."""
    from .config import BACKEND_DIR

    if not settings.ai_enabled:
        return ["COPILOT_AI_ENABLED=false i .env."]
    env = BACKEND_DIR / ".env"
    hints = [f"Fant ingen ANTHROPIC_API_KEY. Backend leser: {env}"]
    if not env.exists() and not (BACKEND_DIR / ".env.txt").exists():
        hints.append("Filen .env finnes ikke i denne mappen.")
    example = BACKEND_DIR / ".env.example"
    try:
        for raw in example.read_text(encoding="utf-8-sig").splitlines():
            if raw.strip().startswith("ANTHROPIC_API_KEY=sk-"):
                hints.append("Nokkelen ligger i .env.example - flytt linjen til .env.")
    except OSError:
        pass
    try:
        text = env.read_text(encoding="utf-8-sig") if env.exists() else ""
        if "# ANTHROPIC_API_KEY" in text and "\nANTHROPIC_API_KEY" not in "\n" + text:
            hints.append("Linjen starter med # (kommentar). Fjern # foran ANTHROPIC_API_KEY.")
    except OSError:
        pass
    hints.append("Legg linjen ANTHROPIC_API_KEY=sk-ant-... nederst i .env og start paa nytt.")
    return hints


def main() -> None:
    import sys

    import uvicorn

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    settings = get_settings()
    busy = port_in_use_message(settings.host, settings.port)
    if busy:
        print(f"\n  FEIL: {busy}\n")
        sys.exit(3)
    token = load_or_create_token(settings)
    print("\n  AI Trading Copilot backend")
    print(f"  URL:   http://{settings.host}:{settings.port}")
    print(f"  Mode:  {settings.mode.value} (read-only - places no trades)")
    print(f"  Token: {token}")
    if settings.anthropic_api_key and settings.ai_enabled:
        print(f"  AI:    {settings.ai_model}, maks {settings.ai_monthly_budget_nok:.0f} kr/mnd")
    else:
        print("  AI:    av")
        for line in ai_key_diagnosis(settings):
            print(f"         {line}")
    print("  Paste the URL and token into the extension's options page.\n")
    uvicorn.run(create_app(settings), host=settings.host, port=settings.port, log_level="info")
