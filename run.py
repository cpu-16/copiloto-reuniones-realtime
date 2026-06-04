"""Punto de entrada: levanta el orquestador con el pipeline de audio y abre la ventana.
Uso:
    python run.py              # abre la ventana flotante (pywebview)
    python run.py --no-window  # solo servidor; abre la UI en tu navegador
Requiere config.toml (copia de config.example.toml)."""
from __future__ import annotations

import asyncio
import sys
import threading
import time

import uvicorn

from asistente.config import load_config
from asistente.brain.claude_client import WarmClaude
from asistente.capture.pipewire import PipeWireCapture
from asistente.transcribe.whisper_stt import LiveTranscriber
from asistente.events import TranscriptFinal, TranscriptPartial
from asistente.server.app import create_app
from asistente.ui.launcher import open_window


def main() -> None:
    cfg = load_config("config.toml")
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

    def on_final(text: str) -> None:
        print("[final]", text)  # eco en terminal para diagnóstico
        _push(TranscriptFinal(text=text, ts=0.0))

    def on_partial(text: str) -> None:
        _push(TranscriptPartial(text=text, ts=0.0))

    cap = PipeWireCapture(target=cfg.audio.target, rate=cfg.audio.sample_rate)
    trans = LiveTranscriber(
        model=cfg.whisper.model, language=cfg.whisper.language,
        compute_type=cfg.whisper.compute_type, realtime_model=cfg.whisper.realtime_model,
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

    url = f"http://{cfg.server.host}:{cfg.server.port}/?token={cfg.server.token}"
    try:
        if "--no-window" in sys.argv:
            print(f"\n  Servidor listo. Abre esta URL en tu navegador:\n  {url}\n")
            print("  (Ctrl+C para detener)")
            threading.Event().wait()  # bloquea hasta Ctrl+C
        else:
            print("Abriendo ventana:", url)
            open_window(url)  # bloquea hasta cerrar la ventana
    except KeyboardInterrupt:
        pass
    finally:
        trans.stop()
        cap.stop()
        brain.stop()


if __name__ == "__main__":
    main()
