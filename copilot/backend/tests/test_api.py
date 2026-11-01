import pytest
from starlette.websockets import WebSocketDisconnect

from .conftest import EXT_ID, TOKEN

AUTH = {"Authorization": f"Bearer {TOKEN}"}
EXT_ORIGIN = {"origin": f"chrome-extension://{EXT_ID}"}


def test_health_is_public(client):
    r = client.get("/api/health")
    assert r.status_code == 200 and r.json()["ok"]


def test_status_requires_token(client):
    assert client.get("/api/status").status_code == 401
    assert client.get("/api/status", headers={"Authorization": "Bearer nope"}).status_code == 401
    r = client.get("/api/status", headers=AUTH)
    assert r.status_code == 200
    body = r.json()
    assert body["readOnly"] is True
    assert body["feed"]["synthetic"] is True


def recv_until(ws, type_, limit=5000):
    for _ in range(limit):
        m = ws.receive_json()
        if m["type"] == type_:
            return m
    raise AssertionError(f"no {type_} message")


def test_ws_full_flow(client):
    with client.websocket_connect("/ws", headers=EXT_ORIGIN) as ws:
        ws.send_json({"type": "auth", "token": TOKEN})
        hello = ws.receive_json()
        assert hello["type"] == "hello"
        assert hello["data"]["readOnly"] is True and hello["data"]["mode"] == "demo"
        tick = recv_until(ws, "tick")["data"]
        assert tick["symbol"] == "XAUUSD" and tick["ask"] >= tick["bid"]
        candle = recv_until(ws, "candle")["data"]
        assert candle["l"] <= candle["o"] <= candle["h"]
        ws.send_json({"type": "ping", "t": 123})
        assert recv_until(ws, "pong")["data"]["t"] == 123


def test_ws_bad_token_closed(client):
    with client.websocket_connect("/ws", headers=EXT_ORIGIN) as ws:
        ws.send_json({"type": "auth", "token": "wrong"})
        assert ws.receive_json()["data"]["code"] == "unauthorized"
        with pytest.raises(WebSocketDisconnect) as exc:
            ws.receive_json()
        assert exc.value.code == 4401


def test_ws_foreign_origin_rejected(client):
    with pytest.raises(WebSocketDisconnect):
        with client.websocket_connect("/ws", headers={"origin": "https://evil.example"}) as ws:
            ws.receive_json()


def test_ws_unpinned_extension_rejected(client):
    with pytest.raises(WebSocketDisconnect):
        with client.websocket_connect("/ws", headers={"origin": "chrome-extension://" + "b" * 32}) as ws:
            ws.receive_json()
