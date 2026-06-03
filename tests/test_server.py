import pytest
from httpx import ASGITransport, AsyncClient
from starlette.testclient import TestClient

from asistente.server.app import create_app
from asistente.config import Config


@pytest.mark.asyncio
async def test_health_ok():
    app = create_app(Config(), brain=None, start_audio=False)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://t") as c:
        r = await c.get("/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


def test_ws_rechaza_token_malo():
    cfg = Config()  # token por defecto "cambia-este-token"
    app = create_app(cfg, brain=None, start_audio=False)
    client = TestClient(app)
    import websockets.exceptions  # noqa
    from starlette.websockets import WebSocketDisconnect
    with pytest.raises(WebSocketDisconnect):
        with client.websocket_connect("/ws?token=malo") as ws:
            ws.receive_text()


def test_ws_acepta_token_bueno():
    cfg = Config()
    app = create_app(cfg, brain=None, start_audio=False)
    client = TestClient(app)
    with client.websocket_connect(f"/ws?token={cfg.server.token}") as ws:
        msg = ws.receive_json()
        assert msg["type"] == "status"
        assert msg["state"] == "capturando"
