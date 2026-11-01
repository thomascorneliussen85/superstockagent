"""WebSocket endpoint ``/ws``.

Handshake
---------
1. Origin is validated before the socket is accepted (rejected => 403).
2. The client must send ``{"type": "auth", "token": "..."}`` within the
   auth timeout. The token is not put in the URL so it never ends up in logs
   or browser history.
3. Server replies ``hello`` followed by a snapshot (status, symbol spec,
   candle history, last tick), then streams live messages.

Client messages after auth: ``{"type": "ping"}`` -> ``pong``.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging

from fastapi import APIRouter, WebSocket, WebSocketDisconnect, status

from .. import PROTOCOL_VERSION, __version__
from ..security import token_matches

log = logging.getLogger(__name__)
router = APIRouter()

CLOSE_UNAUTHORIZED = 4401
CLOSE_FORBIDDEN_ORIGIN = 4403


@router.websocket("/ws")
async def ws_endpoint(ws: WebSocket) -> None:
    app = ws.app
    settings = app.state.settings
    origin = ws.headers.get("origin")
    if not app.state.origin_policy.is_allowed(origin):
        log.warning("Rejected WebSocket from origin %r", origin)
        await ws.close(code=status.WS_1008_POLICY_VIOLATION)
        return

    await ws.accept()
    try:
        raw = await asyncio.wait_for(ws.receive_text(), timeout=settings.ws_auth_timeout_seconds)
        msg = json.loads(raw)
    except (TimeoutError, json.JSONDecodeError, WebSocketDisconnect):
        with contextlib.suppress(Exception):
            await ws.close(code=CLOSE_UNAUTHORIZED)
        return

    if not (
        isinstance(msg, dict)
        and msg.get("type") == "auth"
        and token_matches(app.state.token, msg.get("token"))
    ):
        await ws.send_json({"type": "error", "data": {"code": "unauthorized"}})
        await ws.close(code=CLOSE_UNAUTHORIZED)
        return

    hub = app.state.hub
    sub = hub.subscribe(settings.ws_queue_size)
    await ws.send_json(
        {
            "type": "hello",
            "data": {
                "serverVersion": __version__,
                "protocol": PROTOCOL_VERSION,
                "mode": hub.mode,
                "readOnly": True,
                "symbol": settings.symbol,
            },
        }
    )
    for m in hub.snapshot():
        await ws.send_json(m)

    async def pump() -> None:
        while True:
            try:
                m = await asyncio.wait_for(sub.queue.get(), timeout=settings.heartbeat_seconds)
            except TimeoutError:
                m = {"type": "heartbeat", "data": hub.status_payload()}
            await ws.send_json(m)

    background: set[asyncio.Task] = set()

    async def reader() -> None:
        while True:
            raw = await ws.receive_text()
            try:
                m = json.loads(raw)
            except json.JSONDecodeError:
                continue
            if not isinstance(m, dict):
                continue
            if m.get("type") == "ping":
                await ws.send_json({"type": "pong", "data": {"t": m.get("t")}})
            elif m.get("type") == "ai_request":
                app.state.ai.request_manual()
            elif str(m.get("type", "")).startswith("replay_") or m.get("type") == "replay_ai":
                task = asyncio.create_task(app.state.replay.command(m))
                background.add(task)  # keep a reference until done
                task.add_done_callback(background.discard)

    tasks = [asyncio.create_task(pump()), asyncio.create_task(reader())]
    try:
        done, pending = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
        for t in pending:
            t.cancel()
        for t in done:
            exc = t.exception()
            if exc and not isinstance(exc, WebSocketDisconnect):
                log.debug("WebSocket task ended: %r", exc)
    finally:
        for t in tasks:
            t.cancel()
        hub.unsubscribe(sub)
