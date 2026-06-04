"""Orquestador: sirve la UI, expone /ws (transcripción + sugerencias) y arranca
el pipeline captura->transcripción. El cerebro (Claude) atiende 'ask' a demanda."""
from __future__ import annotations

import asyncio
from pathlib import Path

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles

from asistente.config import Config
from asistente.events import Status, Suggestion, Toggle, parse_client_event, AskCommand

WEB_DIR = Path(__file__).resolve().parent.parent / "ui" / "web"


def _ask_prompt(ctx, question: str) -> str:
    """Arma el prompt de una pregunta manual incluyendo el contexto reciente."""
    contexto = "\n".join(ctx) if ctx else ""
    if not contexto:
        return question
    return (
        f"Contexto reciente de la reunión:\n{contexto}\n\n"
        f"Pregunta del usuario: {question}\n\n"
        f"Responde de forma breve y útil en español."
    )


def create_app(cfg: Config, brain=None, start_audio: bool = True) -> FastAPI:
    # `start_audio` se conserva por estabilidad de firma; run.py (Task 13) arranca el pipeline.
    _ = start_audio
    app = FastAPI()
    app.state.cfg = cfg
    app.state.brain = brain
    app.state.clients: set[WebSocket] = set()

    @app.get("/health")
    async def health():
        return {"status": "ok"}

    @app.get("/", response_class=HTMLResponse)
    async def index():
        path = WEB_DIR / "index.html"
        if path.exists():
            return path.read_text()
        return "<html><body>UI no instalada todavía.</body></html>"

    app.mount("/static", StaticFiles(directory=str(WEB_DIR), check_dir=False), name="static")

    async def broadcast(model) -> None:
        dead = []
        for ws in list(app.state.clients):   # snapshot: evita mutación del set durante await
            try:
                await ws.send_text(model.model_dump_json())
            except Exception:
                dead.append(ws)
        for ws in dead:
            app.state.clients.discard(ws)

    app.state.broadcast = broadcast

    @app.get("/toggle")
    async def toggle(token: str = ""):
        """Atajo global: alterna la visibilidad de la ventana (vía un atajo de GNOME
        que hace curl a esta ruta). Difunde un evento toggle a las UIs conectadas."""
        if token != cfg.server.token:
            return {"ok": False}
        await broadcast(Toggle())
        return {"ok": True}

    @app.websocket("/ws")
    async def ws_endpoint(ws: WebSocket):
        token = ws.query_params.get("token")
        if token != cfg.server.token:
            await ws.close(code=4401)
            return
        await ws.accept()
        app.state.clients.add(ws)
        await ws.send_text(Status(state="capturando").model_dump_json())
        try:
            while True:
                raw = await ws.receive_text()
                cmd = parse_client_event(raw)
                if isinstance(cmd, AskCommand) and app.state.brain:
                    await ws.send_text(Status(state="pensando").model_dump_json())
                    try:
                        prompt = _ask_prompt(getattr(app.state, "ctx", None), cmd.text)
                        answer = await asyncio.to_thread(app.state.brain.ask, prompt)
                        await ws.send_text(Suggestion(text=answer, ready=True).model_dump_json())
                    except Exception as e:
                        await ws.send_text(
                            Status(state="error", detail=str(e)).model_dump_json()
                        )
        except WebSocketDisconnect:
            app.state.clients.discard(ws)

    # El arranque del pipeline de audio se hace en run.py (Task 13), no aquí.
    return app
