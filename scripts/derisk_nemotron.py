#!/usr/bin/env python
"""De-risk C0 de la migración a Nemotron streaming. PUERTA DE VERIFICACIÓN.

Corre con el venv .venv-nemotron (NeMo 26.06+) y una GPU. Carga el modelo, simula
streaming en vivo alimentando un wav por chunks a NemotronTranscriber, e imprime
parciales/finales + latencia. Si esto NO convence, se ABORTA la migración y se cae al
respaldo parakeet+boosting.

Uso:
    .venv-nemotron/bin/python scripts/derisk_nemotron.py --wav muestra_es.wav \
        --att 56,13 --lang es --glossary "Kubernetes,Rafael Valdés"

El wav ideal: español tuyo con tus términos. Se remuestrea a 16k mono.
"""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

import numpy as np


def load_pcm16(path: str, sr: int = 16000) -> bytes:
    """Carga un audio a PCM s16 mono al sample rate dado."""
    try:
        import librosa  # NeMo lo trae
        y, _ = librosa.load(path, sr=sr, mono=True)
    except Exception as e:  # noqa: BLE001
        print(f"No pude cargar {path} con librosa: {e}")
        sys.exit(1)
    return (np.clip(y, -1.0, 1.0) * 32767).astype("<i2").tobytes()


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--wav", required=True, help="audio de prueba (español, con tus términos)")
    ap.add_argument("--model", default="nvidia/nemotron-3.5-asr-streaming-0.6b")
    ap.add_argument("--att", default="56,13", help="att_context_size, ej 56,13 | 56,6 | 56,3")
    ap.add_argument("--lang", default="es")
    ap.add_argument("--glossary", default="", help="términos separados por coma")
    ap.add_argument("--chunk-ms", type=int, default=100, help="tamaño de chunk de alimentación")
    args = ap.parse_args()

    if not Path(args.wav).exists():
        print(f"No existe el wav: {args.wav}")
        sys.exit(1)

    att = [int(x) for x in args.att.split(",")]
    glossary = [t.strip() for t in args.glossary.split(",") if t.strip()]

    print(f"Cargando {args.model} (att={att}, lang={args.lang})… puede tardar.")
    from asistente.transcribe.nemotron_stt import NemotronTranscriber

    t0 = time.monotonic()
    finals: list[str] = []

    def on_partial(text: str) -> None:
        print(f"  [parcial +{time.monotonic()-t0:5.1f}s] {text}")

    def on_final(text: str) -> None:
        finals.append(text)
        print(f"[FINAL +{time.monotonic()-t0:5.1f}s] {text}")

    trans = NemotronTranscriber(
        model_name=args.model, att_context_size=att, target_lang=args.lang,
        glossary=glossary, on_final=on_final, on_partial=on_partial,
    )
    print(f"Modelo cargado en {time.monotonic()-t0:.1f}s. Streaming…")

    pcm = load_pcm16(args.wav)
    sr = 16000
    chunk_bytes = int(sr * args.chunk_ms / 1000) * 2
    # +2s de silencio al final para que el endpointing cierre la última frase.
    pcm += b"\x00\x00" * sr * 2

    def feeder():
        for i in range(0, len(pcm), chunk_bytes):
            yield pcm[i:i + chunk_bytes]
            time.sleep(args.chunk_ms / 1000)   # ritmo "tiempo real"

    t0 = time.monotonic()
    trans.start(feeder(), sample_rate=sr)
    # Espera a que termine de consumir + colita.
    dur_s = len(pcm) / (sr * 2)
    time.sleep(dur_s + 3)
    trans.stop()

    print("\n===== RESULTADO =====")
    print(f"Finales: {len(finals)}")
    print("Transcripción:", " ".join(finals))
    _probe_context_biasing(args.model, glossary)


def _probe_context_biasing(model_name: str, glossary: list[str]) -> None:
    """Verifica si el RNN-T de este NeMo acepta phrase boosting (glosario nativo)."""
    print("\n----- context biasing / phrase boosting -----")
    try:
        from nemo.collections.asr.parts.context_biasing.boosting_graph_batched import (
            BoostingTreeModelConfig,
        )
        BoostingTreeModelConfig(key_phrases_list=glossary or ["prueba"])
        print("✓ BoostingTreeModelConfig disponible (key_phrases_list).")
        print("  → Si change_decoding_strategy lo acepta en el decoder greedy, el glosario")
        print("    nativo es viable; si no, queda la corrección por similitud (ya activa).")
    except Exception as e:  # noqa: BLE001
        print(f"✗ Phrase boosting no disponible aquí: {e}")
        print("  → Se usa la corrección por similitud (correct.py).")


if __name__ == "__main__":
    main()
