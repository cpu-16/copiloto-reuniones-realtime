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


class _FakeBrain:
    def ask(self, prompt):
        return "respuesta-fake"


def test_ws_ask_responde_answer_con_tab():
    cfg = Config()
    app = create_app(cfg, brain=_FakeBrain(), start_audio=False)
    client = TestClient(app)
    with client.websocket_connect(f"/ws?token={cfg.server.token}") as ws:
        ws.receive_json()  # status capturando inicial
        ws.send_json({"type": "ask", "text": "dame ideas", "tab": "ideas"})
        msgs = [ws.receive_json() for _ in range(3)]  # pensando, answer, capturando
    ans = next(m for m in msgs if m["type"] == "answer")
    assert ans["tab"] == "ideas"
    assert ans["text"] == "respuesta-fake"


def test_ws_briefing_set_fija_contexto_y_difunde():
    from asistente.context import SessionContext
    cfg = Config()
    app = create_app(cfg, brain=None, start_audio=False)
    app.state.ctx = SessionContext()
    client = TestClient(app)
    with client.websocket_connect(f"/ws?token={cfg.server.token}") as ws:
        ws.receive_json()  # status capturando inicial
        ws.send_json({"type": "briefing.set", "text": "Proyecto Acme, objetivo X"})
        msg = ws.receive_json()
        assert msg["type"] == "briefing.state"
        assert msg["text"] == "Proyecto Acme, objetivo X"
    assert "Acme" in app.state.ctx.briefing


def test_ask_prompt_usa_compose_del_contexto():
    from asistente.context import SessionContext
    from asistente.server.app import _ask_prompt
    ctx = SessionContext()
    ctx.set_briefing("Proyecto Acme")
    ctx.add_final("hablamos del despliegue")
    prompt = _ask_prompt(ctx, "¿qué hago?")
    assert "Acme" in prompt and "despliegue" in prompt and "¿qué hago?" in prompt
    # sin contexto, devuelve la pregunta tal cual
    assert _ask_prompt(None, "hola") == "hola"


def test_ghost_endpoint_valida_token():
    cfg = Config()
    app = create_app(cfg, brain=None, start_audio=False)
    client = TestClient(app)
    assert client.get(f"/ghost?token={cfg.server.token}").json()["ok"] is True
    assert client.get("/ghost?token=malo").json()["ok"] is False


def test_ws_capture_pausa_y_difunde_status():
    cfg = Config()
    app = create_app(cfg, brain=None, start_audio=False)
    client = TestClient(app)
    with client.websocket_connect(f"/ws?token={cfg.server.token}") as ws:
        ws.receive_json()  # capturando
        ws.send_json({"type": "capture", "paused": True})
        msg = ws.receive_json()
        assert msg["type"] == "status"
        assert msg["state"] == "pausado"
    assert app.state.paused.is_set()
