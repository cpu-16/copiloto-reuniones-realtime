"""De-risk de Parakeet TDT 0.6B v3 (NeMo): ¿instala, transcribe español, latencia, VRAM?

Correr con el venv aislado:
    .venv-parakeet/bin/python scripts/derisk_parakeet.py prueba.wav
"""
import sys
import time

import torch


def main() -> None:
    audio = sys.argv[1] if len(sys.argv) > 1 else "prueba.wav"
    print("Importando NeMo ASR...")
    import nemo.collections.asr as nemo_asr

    print("Cargando nvidia/parakeet-tdt-0.6b-v3 (descarga ~1.2GB la 1ª vez)...")
    t0 = time.perf_counter()
    model = nemo_asr.models.ASRModel.from_pretrained("nvidia/parakeet-tdt-0.6b-v3")
    model = model.to("cuda").eval()
    print(f"Modelo cargado en {time.perf_counter() - t0:.1f}s")

    torch.cuda.reset_peak_memory_stats()
    # duración del audio para calcular RTFx
    import wave
    with wave.open(audio, "rb") as w:
        dur = w.getnframes() / w.getframerate()

    t1 = time.perf_counter()
    out = model.transcribe([audio])
    dt = time.perf_counter() - t1

    # NeMo nuevo devuelve Hypothesis con .text; viejo devuelve str
    first = out[0]
    text = getattr(first, "text", first)
    vram = torch.cuda.max_memory_allocated() / 1e9

    print("\n===== RESULTADO =====")
    print(f"Audio        : {dur:.1f}s")
    print(f"Transcripción: {text}")
    print(f"Tiempo       : {dt:.2f}s  (RTFx ~{dur / dt:.0f}x)")
    print(f"VRAM pico    : {vram:.2f} GB")
    if not str(text).strip():
        print("ADVERTENCIA: transcripción vacía")
        sys.exit(1)


if __name__ == "__main__":
    main()
