"""Application configuration.

All settings can be overridden with environment variables prefixed ``COPILOT_``
or via a ``.env`` file in the backend directory. Secrets (API keys, the local
auth token) are never hard-coded.
"""

from __future__ import annotations

from enum import StrEnum
from functools import lru_cache
from pathlib import Path

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parent.parent


class TradingMode(StrEnum):
    """Where market/account data comes from.

    ``demo`` uses a synthetic price generator and touches no broker at all.
    ``mt5`` connects to the logged-in MT5 terminal and reports whether the
    account is demo or live. ``mt5_demo`` / ``mt5_live`` additionally refuse
    to run if the account type does not match. All MT5 modes are read-only.
    """

    DEMO = "demo"
    MT5 = "mt5"
    MT5_DEMO = "mt5_demo"
    MT5_LIVE = "mt5_live"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="COPILOT_",
        env_file=BACKEND_DIR / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    host: str = "127.0.0.1"
    port: int = 8765

    mode: TradingMode = TradingMode.DEMO
    symbol: str = "XAUUSD"

    # Where the local auth token is stored (created on first start).
    data_dir: Path = BACKEND_DIR / "data"
    auth_token: str | None = Field(
        default=None,
        description="Optional fixed token. If unset, one is generated and stored in data_dir.",
    )

    # Origin validation. Extension IDs are pinned when set; when empty any
    # chrome-extension:// origin is accepted (token still required) and a
    # warning is logged.
    allowed_extension_ids: list[str] = Field(default_factory=list)
    allowed_web_origins: list[str] = Field(
        default_factory=lambda: ["http://localhost:5173", "http://127.0.0.1:5173"]
    )

    # MetaTrader 5 (read-only).
    mt5_symbol: str | None = Field(
        default=None, description="Broker symbol name if not XAUUSD (e.g. XAUUSD.m, GOLD)"
    )
    mt5_path: str | None = Field(default=None, description="Path to terminal64.exe (optional)")
    mt5_utc_offset_minutes: int | None = Field(
        default=None, description="Broker server time minus UTC. Auto-detected when unset."
    )
    mt5_poll_interval_seconds: float = 0.1

    # Demo feed parameters.
    demo_start_price: float = 4000.0
    demo_seed: int | None = None

    # Data freshness: a feed with no tick for this long is reported stale.
    stale_after_seconds: float = 5.0
    heartbeat_seconds: float = 15.0
    ws_auth_timeout_seconds: float = 5.0
    ws_queue_size: int = 500
    analysis_interval_seconds: float = 1.0

    @field_validator("host")
    @classmethod
    def _local_only(cls, v: str) -> str:
        # The backend exposes account data; it must never listen on a public interface.
        if v not in {"127.0.0.1", "localhost", "::1"}:
            raise ValueError("Backend must bind to a loopback address (127.0.0.1/localhost/::1)")
        return v

    @property
    def uses_mt5(self) -> bool:
        return self.mode is not TradingMode.DEMO


@lru_cache
def get_settings() -> Settings:
    return Settings()
