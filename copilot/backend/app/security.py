"""Local authentication and origin validation.

The backend only listens on loopback, but any web page the user visits can
still try to reach ``ws://127.0.0.1``. Two independent checks protect it:

1. **Origin validation** – browsers always send ``Origin`` on WebSocket
   handshakes; only the extension (and the local dev page) are accepted.
2. **Bearer token** – a random secret generated on first start and pasted
   into the extension's options page. Compared in constant time.
"""

from __future__ import annotations

import hmac
import logging
import os
import secrets
from pathlib import Path

from .config import Settings

log = logging.getLogger(__name__)

TOKEN_FILENAME = "auth_token"


def load_or_create_token(settings: Settings) -> str:
    if settings.auth_token:
        return settings.auth_token
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    path: Path = settings.data_dir / TOKEN_FILENAME
    if path.exists():
        token = path.read_text(encoding="utf-8").strip()
        if len(token) >= 32:
            return token
        log.warning("Stored auth token is too short; generating a new one")
    token = secrets.token_urlsafe(32)
    path.write_text(token, encoding="utf-8")
    try:
        os.chmod(path, 0o600)
    except OSError:  # pragma: no cover - Windows ignores POSIX modes
        pass
    log.info("Generated new local auth token at %s", path)
    return token


def token_matches(expected: str, provided: str | None) -> bool:
    if not provided:
        return False
    return hmac.compare_digest(expected.encode(), provided.encode())


def parse_bearer(header_value: str | None) -> str | None:
    if not header_value:
        return None
    scheme, _, value = header_value.partition(" ")
    if scheme.lower() != "bearer" or not value:
        return None
    return value.strip()


class OriginPolicy:
    def __init__(self, settings: Settings) -> None:
        self._extension_ids = {i.strip() for i in settings.allowed_extension_ids if i.strip()}
        self._web_origins = {o.rstrip("/") for o in settings.allowed_web_origins}
        if not self._extension_ids:
            log.warning(
                "COPILOT_ALLOWED_EXTENSION_IDS is empty: any chrome-extension origin is accepted "
                "(the auth token is still required). Pin your extension ID for stronger isolation."
            )

    def is_allowed(self, origin: str | None) -> bool:
        if not origin:
            # Non-browser clients (tests, CLI tools) send no Origin. They still need the token.
            return True
        origin = origin.rstrip("/")
        if origin.startswith("chrome-extension://"):
            ext_id = origin.removeprefix("chrome-extension://")
            return not self._extension_ids or ext_id in self._extension_ids
        return origin in self._web_origins

    @property
    def cors_origins(self) -> list[str]:
        return sorted(self._web_origins)

    @property
    def cors_origin_regex(self) -> str | None:
        if self._extension_ids:
            ids = "|".join(sorted(self._extension_ids))
            return rf"chrome-extension://({ids})"
        return r"chrome-extension://[a-p]{32}"
