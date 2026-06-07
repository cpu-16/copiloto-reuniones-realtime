"""Orquestador: sirve la UI, expone /ws (transcripción + sugerencias) y arranca
el pipeline captura->transcripción. El cerebro (Claude) atiende 'ask' a demanda."""
from __future__ import annotations

import asyncio
import threading
from pathlib import Path

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles

from asistente.config import Config
from asistente.events import (
    Status, Suggestion, Answer, Toggle, BriefingSet, BriefingState, parse_client_event,
    AskCommand, CaptureCommand,
)

WEB_DIR = Path(__file__).resolve().parent.parent / "ui" / "web"


def _ask_prompt(ctx, question: str) -> str:
    """Arma el prompt de una pregunta manual incluyendo el contexto de la sesión
    (briefing + resumen + ventana, vía SessionContext.compose)."""
    contexto = ctx.compose() if ctx is not None and hasattr(ctx, "compose") else ""
    if not contexto:
        return question
    return (
        f"{contexto}\n\n"
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
    # Pausa de captura: si está seteado, run.py descarta parciales/finales (no transcribe,
    # no entra al contexto, no va a Claude). pw-record y el transcriptor siguen vivos.
    app.state.paused = threading.Event()

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
                if isinstance(cmd, CaptureCommand):
                    # Pausa/reanuda; difunde el estado a TODAS las UIs para sincronizar.
                    if cmd.paused:
                        app.state.paused.set()
                    else:
                        app.state.paused.clear()
                    await broadcast(Status(state="pausado" if cmd.paused else "capturando"))
                elif isinstance(cmd, BriefingSet):
                    # Fija el briefing durable y lo difunde para sincronizar las UIs.
                    ctx = getattr(app.state, "ctx", None)
                    if ctx is not None and hasattr(ctx, "set_briefing"):
                        ctx.set_briefing(cmd.text)
                    await broadcast(BriefingState(text=cmd.text))
                elif isinstance(cmd, AskCommand) and app.state.brain:
                    paused = app.state.paused.is_set()
                    await ws.send_text(Status(state="pensando").model_dump_json())
                    try:
                        prompt = _ask_prompt(getattr(app.state, "ctx", None), cmd.text)
                        answer = await asyncio.to_thread(app.state.brain.ask, prompt)
                        # Respuesta a pedido → panel lateral (Answer), no la tarjeta proactiva.
                        await ws.send_text(
                            Answer(tab=cmd.tab or "libre", text=answer).model_dump_json()
                        )
                        # Si está pausado no piso el estado "pausado"; si no, vuelvo a capturar.
                        await ws.send_text(
                            Status(state="pausado" if paused else "capturando").model_dump_json()
                        )
                    except Exception as e:
                        await ws.send_text(
                            Status(state="error", detail=str(e)).model_dump_json()
                        )
        except WebSocketDisconnect:
            app.state.clients.discard(ws)

    # El arranque del pipeline de audio se hace en run.py (Task 13), no aquí.
    return app
