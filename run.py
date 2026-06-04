"""Punto de entrada: levanta el orquestador con el pipeline de audio y abre la ventana.
Uso:
    python run.py              # abre la ventana flotante (pywebview)
    python run.py --no-window  # solo servidor; abre la UI en tu navegador
Requiere config.toml (copia de config.example.toml)."""
from __future__ import annotations

import asyncio
import os
import socket
import sys
import threading
import time
from collections import deque

import uvicorn

from asistente.config import load_config
from asistente.brain.claude_client import WarmClaude
from asistente.capture.pipewire import PipeWireCapture
from asistente.events import TranscriptFinal, TranscriptPartial, Suggestion, Status, Insight
from asistente.detect import is_question_for_me
from asistente.transcribe.clean import is_hallucination
from asistente.copilot import build_copilot_prompt, parse_copilot
from asistente.server.app import create_app
from asistente.ui.launcher import open_window


def _port_free(host: str, port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        try:
            s.bind((host, port))
            return True
        except OSError:
            return False


def main() -> None:
    cfg = load_config("config.toml")
    if not _port_free(cfg.server.host, cfg.server.port):
        print(f"\n  ⚠  Ya hay algo escuchando en {cfg.server.host}:{cfg.server.port}.")
        print("     Seguramente otra instancia del asistente sigue corriendo.")
        print("     Ciérrala primero:  pkill -f run.py   (o cierra su ventana)\n")
        sys.exit(1)
    print("Iniciando cerebro Claude...")
    brain = WarmClaude(model=cfg.claude.model)
    app = create_app(cfg, brain=brain, start_audio=False)

    # Captura + transcripción en hilos; empuja transcript al broadcast del server.
    loop = asyncio.new_event_loop()

    def _push(ev) -> None:
        fut = asyncio.run_coroutine_threadsafe(app.state.broadcast(ev), loop)
        try:
            fut.result(timeout=2)
        except Exception:
            pass

    # Buffer rodante de contexto reciente para alimentar a Claude.
    # Lo compartimos con el servidor para que el "preguntar" manual también
    # use el contexto de la reunión, no solo el proactivo.
    ctx = deque(maxlen=12)
    app.state.ctx = ctx
    names = cfg.user.names
    yo = names[0] if names else "la persona"
    # Estado del copiloto: borrador de respuesta siempre listo + control de novedad.
    cop = {"draft": "", "seen": 0}

    def suggest_for(question: str) -> None:
        """Sugiere respuesta. Si ya hay un borrador listo, lo muestra al instante
        y luego lo refina con la pregunta concreta."""
        if cop["draft"]:
            _push(Suggestion(text=cop["draft"], ready=True))  # instantáneo
        contexto = "\n".join(ctx)
        prompt = (
            f"Eres copiloto de {yo} ({cfg.user.role}). "
            f"Contexto reciente de la reunión:\n{contexto}\n\n"
            f"Acaban de preguntarle algo a {yo}: \"{question}\". "
            f"Sugiere una respuesta breve y natural que {yo} podría decir."
        )
        try:
            _push(Status(state="pensando"))
            ans = brain.ask(prompt)
            _push(Suggestion(text=ans, ready=True))
            _push(Status(state="capturando"))
        except Exception as e:  # noqa: BLE001
            _push(Status(state="error", detail=str(e)))

    def copilot_loop() -> None:
        """Cada intervalo, si hay transcripción nueva, pide al cerebro un resumen +
        ideas + borrador + alerta de decisión/tarea, y lo difunde como Insight."""
        while True:
            time.sleep(max(3.0, cfg.copilot.interval_s))
            if len(ctx) <= cop["seen"]:
                continue  # nada nuevo
            cop["seen"] = len(ctx)
            contexto = "\n".join(ctx)
            try:
                raw = brain.ask(build_copilot_prompt(cfg.user.role, names, contexto))
                p = parse_copilot(raw)
                if p["draft"]:
                    cop["draft"] = p["draft"]
                _push(Insight(summary=p["summary"], ideas=p["ideas"], alert=p["alert"]))
            except Exception as e:  # noqa: BLE001
                print("  copiloto:", e)

    # Cooldown para no disparar la sugerencia muchas veces por la misma pregunta.
    _sg = {"t": 0.0}

    def maybe_suggest(text: str) -> None:
        if not is_question_for_me(text, names):
            return
        now = time.monotonic()
        if now - _sg["t"] < 8.0:   # como mucho una sugerencia cada 8s
            return
        _sg["t"] = now
        print("  -> parece pregunta para ti; pidiendo sugerencia a Claude…")
        threading.Thread(target=suggest_for, args=(text,), daemon=True).start()

    def on_final(text: str) -> None:
        if is_hallucination(text):
            return
        print("[final]", text)  # eco en terminal para diagnóstico
        _push(TranscriptFinal(text=text, ts=0.0))
        ctx.append(text)
        maybe_suggest(text)

    def on_partial(text: str) -> None:
        if is_hallucination(text):
            return
        _push(TranscriptPartial(text=text, ts=0.0))
        # También detectamos sobre el parcial: con audio continuo casi no hay
        # finales, así que si esperáramos al final nunca saldría la sugerencia.
        maybe_suggest(text)

    cap = PipeWireCapture(target=cfg.audio.target, rate=cfg.audio.sample_rate)
    if cfg.engine == "parakeet":
        print("Motor de transcripción: Parakeet (NeMo). Cargando modelo (~40s)…")
        try:
            from asistente.transcribe.parakeet_stt import ParakeetTranscriber
        except ImportError as e:
            print(f"\n  ⚠  engine='parakeet' necesita el venv .venv-parakeet (NeMo): {e}")
            print("     Corre:  .venv-parakeet/bin/python run.py --native\n")
            sys.exit(1)
        trans = ParakeetTranscriber(
            realtime_pause=cfg.whisper.realtime_pause,
            on_final=on_final, on_partial=on_partial,
        )
    else:
        print("Motor de transcripción: Whisper (faster-whisper).")
        try:
            from asistente.transcribe.whisper_stt import LiveTranscriber
        except ImportError as e:
            print(f"\n  ⚠  engine='whisper' necesita el venv .venv (RealtimeSTT): {e}")
            print("     Corre:  .venv/bin/python run.py --native\n")
            sys.exit(1)
        trans = LiveTranscriber(
            model=cfg.whisper.model, language=cfg.whisper.language,
            compute_type=cfg.whisper.compute_type, realtime_model=cfg.whisper.realtime_model,
            realtime_pause=cfg.whisper.realtime_pause, enable_realtime=cfg.whisper.enable_realtime,
            on_final=on_final, on_partial=on_partial,
        )

    def run_server() -> None:
        asyncio.set_event_loop(loop)
        config = uvicorn.Config(app, host=cfg.server.host, port=cfg.server.port,
                                loop="asyncio", log_level="info")
        server = uvicorn.Server(config)
        loop.run_until_complete(server.serve())

    threading.Thread(target=run_server, daemon=True).start()
    time.sleep(2)  # deja levantar el server

    print("Precalentando Claude (prewarm)...")
    try:
        brain.prewarm()
    except Exception as e:
        print("Aviso: prewarm falló:", e)

    trans.start(cap.stream(), sample_rate=cfg.audio.sample_rate)

    if cfg.copilot.enabled:
        print(f"Copiloto continuo activo (cada {cfg.copilot.interval_s:.0f}s).")
        threading.Thread(target=copilot_loop, daemon=True).start()

    url = f"http://{cfg.server.host}:{cfg.server.port}/?token={cfg.server.token}"
    ws_url = f"ws://{cfg.server.host}:{cfg.server.port}/ws?token={cfg.server.token}"
    try:
        if "--no-window" in sys.argv:
            print(f"\n  Servidor listo. Abre esta URL en tu navegador:\n  {url}\n")
            print("  (Ctrl+C para detener)")
            threading.Event().wait()  # bloquea hasta Ctrl+C
        elif "--native" in sys.argv:
            print("Abriendo ventana NATIVA (PySide6)...")
            from asistente.ui.native import open_widget
            open_widget(ws_url)  # bloquea hasta cerrar la ventana
        else:
            print("Abriendo ventana:", url)
            open_window(url)  # bloquea hasta cerrar la ventana (pywebview)
    except KeyboardInterrupt:
        pass
    finally:
        # Cerrar la ventana (✕) debe matar TODO el proceso, sin tener que usar Ctrl+C.
        # Limpiamos best-effort con timeout (RealtimeSTT puede colgarse al apagar) y
        # luego forzamos la salida del proceso.
        def _cleanup() -> None:
            for fn in (trans.stop, cap.stop, brain.stop):
                try:
                    fn()
                except Exception:
                    pass
        th = threading.Thread(target=_cleanup, daemon=True)
        th.start()
        th.join(timeout=3)
        print("Cerrando…")
        os._exit(0)


if __name__ == "__main__":
    main()
