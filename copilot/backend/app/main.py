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
from .api import routes, ws
from .config import Settings, TradingMode, get_settings
from .hub import MarketHub
from .market.demo import DemoMarketSource
from .market.source import MarketDataSource
from .security import OriginPolicy, load_or_create_token

log = logging.getLogger("copilot")


def build_source(settings: Settings) -> MarketDataSource:
    if settings.mode is TradingMode.DEMO:
        return DemoMarketSource(start_price=settings.demo_start_price, seed=settings.demo_seed)
    raise NotImplementedError(
        f"mode {settings.mode.value!r} requires the MT5 connector (Phase 2). Use COPILOT_MODE=demo."
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
        await hub.start()
        log.info(
            "AI Trading Copilot backend %s started (mode=%s, read-only)", __version__, settings.mode.value
        )
        try:
            yield
        finally:
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


def main() -> None:
    import uvicorn

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    settings = get_settings()
    token = load_or_create_token(settings)
    print("\n  AI Trading Copilot backend")
    print(f"  URL:   http://{settings.host}:{settings.port}")
    print(f"  Mode:  {settings.mode.value} (read-only)")
    print(f"  Token: {token}")
    print("  Paste the URL and token into the extension's options page.\n")
    uvicorn.run(create_app(settings), host=settings.host, port=settings.port, log_level="info")
