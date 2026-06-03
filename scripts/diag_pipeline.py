"""Diagnóstico del pipeline en vivo: instrumenta cada límite entre componentes
para localizar dónde se rompe la transcripción.

Uso (con AUDIO EN ESPAÑOL SONANDO):
    source .venv/bin/activate
    python scripts/diag_pipeline.py            # usa el target de config.toml
    python scripts/diag_pipeline.py 122        # fuerza un target

Reporta:
  [B1] bytes capturados y RMS (¿llega audio? ¿es silencio?)
  [B2] que feed_audio no lance
  [B3] frases finales producidas por el transcriptor
  Excepciones en CUALQUIER hilo (que normalmente morirían en silencio).
"""
from __future__ import annotations

import sys
import threading
import time

import numpy as np

from asistente.config import load_config
from asistente.capture.pipewire import PipeWireCapture
from RealtimeSTT import AudioToTextRecorder

# ---- estado compartido para el reporte ----
state = {
    "bytes": 0,
    "max_rms": 0.0,
    "last_rms": 0.0,
    "finals": [],
    "feed_error": None,
    "final_error": None,
    "fed_chunks": 0,
}
running = True


def rms_of(chunk: bytes) -> float:
    if not chunk:
        return 0.0
    a = np.frombuffer(chunk, dtype=np.int16).astype(np.float32)
    if a.size == 0:
        return 0.0
    return float(np.sqrt(np.mean(a * a)))


def main() -> None:
    cfg = load_config("config.toml")
    target = sys.argv[1] if len(sys.argv) > 1 else cfg.audio.target
    rate = cfg.audio.sample_rate
    print(f"[setup] target={target!r}  rate={rate}  modelo={cfg.whisper.model}")

    print("[setup] cargando transcriptor (puede tardar unos segundos)...")
    recorder = AudioToTextRecorder(
        model=cfg.whisper.model,
        language=cfg.whisper.language,
        compute_type=cfg.whisper.compute_type,
        device="cuda",
        use_microphone=False,
        spinner=False,
        post_speech_silence_duration=0.7,
    )
    print("[setup] transcriptor listo.")

    cap = PipeWireCapture(target=target, rate=rate)

    def feed_loop() -> None:
        try:
            for chunk in cap.stream():
                if not running:
                    break
                state["bytes"] += len(chunk)
                state["fed_chunks"] += 1
                r = rms_of(chunk)
                state["last_rms"] = r
                state["max_rms"] = max(state["max_rms"], r)
                recorder.feed_audio(chunk, original_sample_rate=rate)
        except Exception as e:  # noqa: BLE001
            import traceback
            state["feed_error"] = traceback.format_exc()
            print("[B1/B2] EXCEPCIÓN en feed_loop:", e)

    def final_loop() -> None:
        try:
            while running:
                text = recorder.text()
                if text:
                    state["finals"].append(text)
                    print("  [B3] FINAL:", text)
        except Exception as e:  # noqa: BLE001
            import traceback
            state["final_error"] = traceback.format_exc()
            print("[B3] EXCEPCIÓN en final_loop:", e)

    threading.Thread(target=feed_loop, daemon=True).start()
    threading.Thread(target=final_loop, daemon=True).start()

    print("\n>>> PON AUDIO EN ESPAÑOL AHORA. Observando 30s...\n")
    for i in range(15):
        time.sleep(2)
        print(f"[t={(i+1)*2:>2}s] bytes={state['bytes']:>8}  "
              f"chunks={state['fed_chunks']:>5}  rms_actual={state['last_rms']:7.1f}  "
              f"rms_max={state['max_rms']:7.1f}  finals={len(state['finals'])}")

    global running
    running = False
    time.sleep(0.5)
    cap.stop()
    try:
        recorder.shutdown()
    except Exception:
        pass

    print("\n===== RESUMEN =====")
    print(f"Bytes capturados : {state['bytes']}")
    print(f"RMS máximo       : {state['max_rms']:.1f}  (s16: 0..32767; <30 ~ silencio)")
    print(f"Frases finales   : {len(state['finals'])}")
    for f in state["finals"]:
        print("   -", f)
    print(f"Error en feed    : {'SÍ' if state['feed_error'] else 'no'}")
    if state["feed_error"]:
        print(state["feed_error"])
    print(f"Error en final   : {'SÍ' if state['final_error'] else 'no'}")
    if state["final_error"]:
        print(state["final_error"])

    print("\n===== LECTURA =====")
    if state["bytes"] == 0:
        print("B1 ROTO: no se capturó audio. Target equivocado o pw-record falló.")
    elif state["max_rms"] < 30:
        print("B1 SILENCIO: se capturan bytes pero es silencio. El audio NO pasa por ese sink/target.")
    elif state["feed_error"]:
        print("B2 ROTO: feed_audio lanzó excepción (ver arriba).")
    elif state["final_error"]:
        print("B3 ROTO: el transcriptor lanzó excepción (ver arriba).")
    elif not state["finals"]:
        print("B3 SIN FINALES: hay audio con señal pero el transcriptor no produjo frases. "
              "Revisar VAD/modelo en modo live.")
    else:
        print("B1-B3 OK: captura+transcripción funcionan. El problema está en "
              "broadcast/WebSocket (B4-B5) dentro de run.py, no en el transcriptor.")


if __name__ == "__main__":
    main()
