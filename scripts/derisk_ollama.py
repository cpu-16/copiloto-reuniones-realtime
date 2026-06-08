#!/usr/bin/env python
"""De-risk: mide la latencia de un LLM local (Ollama) como cerebro del copiloto.

Responde la pregunta "¿un modelo local responde lo bastante rápido?". Corre un prompt
estilo reunión contra el modelo elegido y mide cuánto tarda (1ª llamada = carga en VRAM,
2ª-3ª = en caliente, que es lo que importa).

Uso:
    python scripts/derisk_ollama.py                       # lista modelos y prueba el default
    python scripts/derisk_ollama.py --model gemma4:e2b    # prueba uno específico
"""
from __future__ import annotations

import argparse
import json
import time
import urllib.request

from asistente.brain.ollama_client import OllamaBrain

PROMPT = (
    "Contexto de la reunión:\nSe habla de migrar el DNS del cliente a Cloudflare y de "
    "instalar Windows Server en Proxmox.\n\nAcaban de preguntarte: \"¿cuántos CTs tienen "
    "en el Proxmox y qué recursos hay disponibles?\". Sugiere una respuesta breve."
)


def list_models(host: str) -> list[str]:
    try:
        with urllib.request.urlopen(f"{host}/api/tags", timeout=5) as r:
            data = json.loads(r.read())
        return [m["name"] for m in data.get("models", [])]
    except Exception as e:  # noqa: BLE001
        print("No pude listar modelos:", e)
        return []


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--host", default="http://127.0.0.1:11434")
    ap.add_argument("--model", default=None)
    ap.add_argument("--runs", type=int, default=3)
    args = ap.parse_args()

    models = list_models(args.host)
    print("Modelos disponibles:", ", ".join(models) or "(ninguno)")
    model = args.model or (models[0] if models else "qwen3.5:9b")
    print(f"\nProbando: {model}\n" + "=" * 50)

    brain = OllamaBrain(model=model, host=args.host)
    for i in range(args.runs):
        t0 = time.monotonic()
        ans = brain.ask(PROMPT)
        dt = time.monotonic() - t0
        etiqueta = "(carga en frío)" if i == 0 else "(en caliente)"
        print(f"\n[{i+1}/{args.runs}] {dt:5.2f}s {etiqueta}")
        print("  →", ans[:200].replace("\n", " "))

    print("\n" + "=" * 50)
    print("Referencia: claude -p caliente ronda ~2-3s. Si el local queda por debajo y la")
    print("respuesta es útil, vale la pena. Recuerda la VRAM: ≤4B junto con el ASR.")


if __name__ == "__main__":
    main()
