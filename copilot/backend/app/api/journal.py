"""Journal REST API (token-protected). Notes, tags and screenshots are the only
things that can be written, and they are stored locally - never sent to MT5."""

from __future__ import annotations

import base64
import re
import time
import uuid
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from pydantic import BaseModel, Field

from ..journal.stats import compute_stats
from .routes import require_token

router = APIRouter(prefix="/api/journal", dependencies=[Depends(require_token)])
MAX_SHOT_BYTES = 6 * 1024 * 1024
SHOT_NAME = re.compile(r"^[a-f0-9]{32}\.(png|jpg|webp)$")


def _filter(trades: list[dict[str, Any]], days: int | None, setup: str | None, direction: str | None):
    if days:
        cutoff = int(time.time() * 1000) - days * 86_400_000
        trades = [t for t in trades if (t["close_ms"] or t["open_ms"]) >= cutoff]
    if setup:
        trades = [t for t in trades if (t.get("setup") or "(uten tag)") == setup]
    if direction in ("long", "short"):
        trades = [t for t in trades if t["direction"] == direction]
    return trades


@router.get("/status")
async def journal_status(request: Request) -> dict:
    j = request.app.state.journal
    return {"available": j.available, "lastSyncMs": j.last_sync_ms, "lastError": j.last_error}


@router.post("/sync")
async def journal_sync(request: Request) -> dict:
    return await request.app.state.journal.sync()


@router.get("/stats")
async def journal_stats(
    request: Request, days: int | None = None, setup: str | None = None, direction: str | None = None
) -> dict:
    trades = _filter(request.app.state.journal.store.trades(), days, setup, direction)
    return compute_stats(trades)


@router.get("/trades")
async def journal_trades(request: Request, limit: int = 300, days: int | None = None) -> dict:
    store = request.app.state.journal.store
    trades = _filter(store.trades(closed_only=False), days, None, None)
    evals = store.evals("feedback")
    out = []
    for t in reversed(trades[-max(1, min(limit, 2000)) :]):
        out.append({**t, "feedback": evals.get(t["position_id"])})
    return {"trades": out}


class NotesIn(BaseModel):
    note: str | None = Field(default=None, max_length=5000)
    setup: str | None = Field(default=None, max_length=60)
    tags: list[str] | None = None


@router.put("/trades/{position_id}")
async def update_trade_notes(position_id: int, body: NotesIn, request: Request) -> dict:
    store = request.app.state.journal.store
    if store.trade(position_id) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "ukjent handel")
    return store.update_notes(position_id, body.note, body.setup, body.tags)


class ShotIn(BaseModel):
    dataUrl: str


@router.post("/trades/{position_id}/screenshot")
async def add_screenshot(position_id: int, body: ShotIn, request: Request) -> dict:
    store = request.app.state.journal.store
    if store.trade(position_id) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "ukjent handel")
    m = re.match(r"^data:image/(png|jpeg|webp);base64,(.+)$", body.dataUrl, re.S)
    if not m:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "kun PNG, JPEG eller WebP")
    data = base64.b64decode(m.group(2), validate=False)
    if len(data) > MAX_SHOT_BYTES:
        raise HTTPException(status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, "bildet er for stort (maks 6 MB)")
    ext = {"png": "png", "jpeg": "jpg", "webp": "webp"}[m.group(1)]
    name = f"{uuid.uuid4().hex}.{ext}"
    store.screenshots_dir.mkdir(parents=True, exist_ok=True)
    (store.screenshots_dir / name).write_bytes(data)
    return store.update_notes(position_id, add_screenshot=name)


@router.get("/screenshots/{name}")
async def get_screenshot(name: str, request: Request) -> Response:
    if not SHOT_NAME.match(name):
        raise HTTPException(status.HTTP_404_NOT_FOUND)
    path = request.app.state.journal.store.screenshots_dir / name
    if not path.exists():
        raise HTTPException(status.HTTP_404_NOT_FOUND)
    media = {"png": "image/png", "jpg": "image/jpeg", "webp": "image/webp"}[name.rsplit(".", 1)[1]]
    return Response(path.read_bytes(), media_type=media)
