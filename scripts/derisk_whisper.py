"""De-risk de transcripción: carga faster-whisper 'turbo' en la GPU y transcribe un WAV.
Uso: python scripts/derisk_whisper.py prueba.wav
Verifica: que cargue en CUDA, que el texto en español sea correcto y mide el tiempo.
"""
import sys
import time

from faster_whisper import WhisperModel


def main() -> None:
    audio = sys.argv[1] if len(sys.argv) > 1 else "prueba.wav"
    print("Cargando modelo 'turbo' en CUDA (float16)...")
    t0 = time.perf_counter()
    model = WhisperModel("turbo", device="cuda", compute_type="float16")
    print(f"Modelo cargado en {time.perf_counter() - t0:.1f}s")

    t1 = time.perf_counter()
    segments, info = model.transcribe(audio, language="es")
    text = " ".join(seg.text for seg in segments)
    dt = time.perf_counter() - t1
    print(f"Idioma detectado: {info.language} (p={info.language_probability:.2f})")
    print(f"Transcripción ({dt:.2f}s):\n{text}")
    if not text.strip():
        print("ADVERTENCIA: transcripción vacía.")
        sys.exit(1)


if __name__ == "__main__":
    main()
