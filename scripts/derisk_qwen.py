"""De-risk de Qwen3-ASR-0.6B (paquete qwen-asr, backend transformers).
¿instala, transcribe español, latencia, VRAM, RAM? Comparar con Parakeet.

Correr:  .venv-qwen/bin/python scripts/derisk_qwen.py prueba.wav
"""
import resource
import sys
import time
import wave

import numpy as np
import torch


def rss_gb() -> float:
    return resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1e6


def main() -> None:
    audio_path = sys.argv[1] if len(sys.argv) > 1 else "prueba.wav"
    with wave.open(audio_path, "rb") as w:
        sr = w.getframerate()
        pcm = w.readframes(w.getnframes())
    arr = np.frombuffer(pcm, dtype=np.int16).astype(np.float32) / 32768.0
    dur = arr.size / sr

    print("Importando qwen_asr...")
    from qwen_asr import Qwen3ASRModel

    print("Cargando Qwen/Qwen3-ASR-0.6B (transformers)...")
    t0 = time.perf_counter()
    model = Qwen3ASRModel.from_pretrained("Qwen/Qwen3-ASR-0.6B")
    print(f"cargado en {time.perf_counter() - t0:.1f}s | RAM {rss_gb():.2f} GB")

    torch.cuda.reset_peak_memory_stats()
    t1 = time.perf_counter()
    # La API acepta path / url / base64 / (np.ndarray, sr). Probamos variantes.
    try:
        out = model.transcribe([(arr, sr)])
    except Exception:
        out = model.transcribe(audio=[(arr, sr)])
    dt = time.perf_counter() - t1

    # normaliza la salida a texto
    r = out[0] if isinstance(out, (list, tuple)) else out
    text = getattr(r, "text", None) or (r.get("text") if isinstance(r, dict) else str(r))
    vram = torch.cuda.max_memory_allocated() / 1e9

    print("\n===== RESULTADO Qwen3-ASR-0.6B =====")
    print(f"Audio   : {dur:.1f}s")
    print(f"Texto   : {text}")
    print(f"Tiempo  : {dt:.2f}s (RTFx ~{dur / dt:.0f}x)")
    print(f"VRAM    : {vram:.2f} GB | RAM pico: {rss_gb():.2f} GB")


if __name__ == "__main__":
    main()
