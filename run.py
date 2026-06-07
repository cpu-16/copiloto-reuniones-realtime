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

import uvicorn

from asistente.config import load_config
from asistente.brain.claude_client import WarmClaude
from asistente.capture.pipewire import PipeWireCapture
from asistente.context import SessionContext, build_summary_prompt, load_briefing_source
from asistente.events import (
    TranscriptFinal, TranscriptPartial, Suggestion, Status, Insight, BriefingState,
)
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

    # Contexto de sesión en 3 capas (briefing durable + resumen acumulativo + ventana
    # rodante). Lo compartimos con el servidor para que el "preguntar" manual, la
    # sugerencia proactiva y el copiloto usen el MISMO contexto compuesto.
    ctx = SessionContext(window=cfg.context.window, summary_every=cfg.context.summary_every)
    ctx.set_briefing(cfg.context.briefing)
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
        contexto = ctx.compose(cfg.context.max_chars)
        prompt = (
            f"Eres copiloto de {yo} ({cfg.user.role}).\n{contexto}\n\n"
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
            if ctx.total <= cop["seen"]:
                continue  # nada nuevo (total es monotónico, no se topa como len(deque))
            cop["seen"] = ctx.total
            contexto = ctx.compose(cfg.context.max_chars)
            try:
                raw = brain.ask(build_copilot_prompt(cfg.user.role, names, contexto))
                p = parse_copilot(raw)
                if p["draft"]:
                    cop["draft"] = p["draft"]
                _push(Insight(summary=p["summary"], ideas=p["ideas"], alert=p["alert"]))
            except Exception as e:  # noqa: BLE001
                print("  copiloto:", e)
            # Resumen acumulativo: menos frecuente, reemplaza al anterior (mantiene el
            # foco entre cambios de tema sin inflar el contexto). Mismo pipe de Claude.
            if ctx.needs_summary():
                nuevas = ctx.take_new_for_summary()
                try:
                    ctx.set_summary(brain.ask(build_summary_prompt(ctx.running_summary, nuevas)))
                except Exception as e:  # noqa: BLE001
                    print("  resumen:", e)

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
        if app.state.paused.is_set():   # captura pausada: descarta todo
            return
        if is_hallucination(text):
            return
        print("[final]", text)  # eco en terminal para diagnóstico
        _push(TranscriptFinal(text=text, ts=0.0))
        ctx.add_final(text)
        maybe_suggest(text)

    def on_partial(text: str) -> None:
        if app.state.paused.is_set():   # captura pausada: descarta todo
            return
        if is_hallucination(text):
            return
        _push(TranscriptPartial(text=text, ts=0.0))
        # También detectamos sobre el parcial: con audio continuo casi no hay
        # finales, así que si esperáramos al final nunca saldría la sugerencia.
        maybe_suggest(text)

    cap = PipeWireCapture(target=cfg.audio.target, rate=cfg.audio.sample_rate)
    if cfg.engine == "nemotron":
        print("Motor de transcripción: Nemotron streaming (NeMo). Cargando modelo…")
        try:
            from asistente.transcribe.nemotron_stt import NemotronTranscriber
        except ImportError as e:
            print(f"\n  ⚠  engine='nemotron' necesita el venv .venv-nemotron (NeMo 26.06+): {e}")
            print("     Corre:  .venv-nemotron/bin/python run.py --native\n")
            sys.exit(1)
        trans = NemotronTranscriber(
            model_name=cfg.nemotron.model,
            att_context_size=cfg.nemotron.att_context_size,
            target_lang=cfg.nemotron.target_lang,
            glossary=cfg.asr.glossary,
            correct_enabled=cfg.asr.correct_enabled,
            on_final=on_final, on_partial=on_partial,
        )
    elif cfg.engine == "parakeet":
        print("Motor de transcripción: Parakeet (NeMo). Cargando modelo (~40s)…")
        try:
            from asistente.transcribe.parakeet_stt import ParakeetTranscriber
        except ImportError as e:
            print(f"\n  ⚠  engine='parakeet' necesita el venv .venv-parakeet (NeMo): {e}")
            print("     Corre:  .venv-parakeet/bin/python run.py --native\n")
            sys.exit(1)
        trans = ParakeetTranscriber(
            realtime_pause=cfg.whisper.realtime_pause,
            silence_rms=cfg.parakeet.silence_rms,
            auto_calibrate=cfg.parakeet.auto_calibrate,
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

    # Ingestión del archivo/ruta de contexto: se lee y resume UNA vez, y entra al briefing.
    if cfg.context.briefing_file:
        material = load_briefing_source(cfg.context.briefing_file)
        if material:
            print(f"Resumiendo material de contexto ({cfg.context.briefing_file})…")
            try:
                resumen = brain.ask(
                    "Resume el siguiente material como briefing breve para una reunión "
                    "(proyecto, objetivos, términos clave), en viñetas:\n\n" + material
                )
                ctx.append_briefing(resumen)
            except Exception as e:  # noqa: BLE001
                print("Aviso: no se pudo resumir el material de contexto:", e)
        else:
            print(f"Aviso: no se encontró material en {cfg.context.briefing_file}")
    if ctx.briefing:
        asyncio.run_coroutine_threadsafe(
            app.state.broadcast(BriefingState(text=ctx.briefing)), loop
        )

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
