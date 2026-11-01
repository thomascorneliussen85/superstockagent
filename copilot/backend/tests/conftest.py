from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app
from app.market.demo import DemoMarketSource

TOKEN = "test-token-" + "x" * 32
EXT_ID = "a" * 32


@pytest.fixture
def settings(tmp_path) -> Settings:
    return Settings(
        data_dir=tmp_path,
        auth_token=TOKEN,
        allowed_extension_ids=[EXT_ID],
        demo_seed=1,
        heartbeat_seconds=0.5,
        ws_auth_timeout_seconds=1.0,
    )


@pytest.fixture
def client(settings):
    # Non-realtime demo source: ticks flow as fast as the event loop allows.
    source = DemoMarketSource(seed=1, realtime=False, pace_seconds=0.002)
    app = create_app(settings, source=source)
    with TestClient(app) as c:
        yield c
