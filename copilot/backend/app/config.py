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
    ``mt5_demo`` / ``mt5_live`` are reserved for Phase 2+ and are always
    read-only in the first version.
    """

    DEMO = "demo"
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

    # Demo feed parameters.
    demo_start_price: float = 4000.0
    demo_seed: int | None = None

    # Data freshness: a feed with no tick for this long is reported stale.
    stale_after_seconds: float = 5.0
    heartbeat_seconds: float = 15.0
    ws_auth_timeout_seconds: float = 5.0
    ws_queue_size: int = 500

    @field_validator("host")
    @classmethod
    def _local_only(cls, v: str) -> str:
        # The backend exposes account data; it must never listen on a public interface.
        if v not in {"127.0.0.1", "localhost", "::1"}:
            raise ValueError("Backend must bind to a loopback address (127.0.0.1/localhost/::1)")
        return v

    @property
    def is_live(self) -> bool:
        return self.mode is TradingMode.MT5_LIVE


@lru_cache
def get_settings() -> Settings:
    return Settings()
