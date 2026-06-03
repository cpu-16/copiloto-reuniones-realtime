"""Orquestador: sirve la UI, expone /ws (transcripción + sugerencias) y arranca
el pipeline captura->transcripción. El cerebro (Claude) atiende 'ask' a demanda."""
from __future__ import annotations

import asyncio
from pathlib import Path

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles

from asistente.config import Config
from asistente.events import Status, Suggestion, parse_client_event, AskCommand

WEB_DIR = Path(__file__).resolve().parent.parent / "ui" / "web"


def create_app(cfg: Config, brain=None, start_audio: bool = True) -> FastAPI:
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
        for ws in app.state.clients:
            try:
                await ws.send_text(model.model_dump_json())
            except Exception:
                dead.append(ws)
        for ws in dead:
            app.state.clients.discard(ws)

    app.state.broadcast = broadcast

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
                        answer = await asyncio.to_thread(app.state.brain.ask, cmd.text)
                        await ws.send_text(Suggestion(text=answer, ready=True).model_dump_json())
                    except Exception as e:
                        await ws.send_text(
                            Status(state="error", detail=str(e)).model_dump_json()
                        )
        except WebSocketDisconnect:
            app.state.clients.discard(ws)

    # El arranque del pipeline de audio se hace en run.py (Task 13), no aquí.
    return app
