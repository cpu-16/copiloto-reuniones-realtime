"""Cerebro alternativo: un LLM LOCAL vía Ollama (sin nube, sin API key).

Mismo interfaz que WarmClaude (`ask` / `prewarm` / `stop`) para que `run.py` lo cablee
igual. Usa la API HTTP de Ollama (`/api/chat`) con la librería estándar (urllib), sin
dependencias nuevas. Pensado para correr AL LADO del ASR: en una GPU de 8GB con Nemotron
(~2.7GB) conviene un modelo ≤4B; uno de 9B solo cabría sin el ASR.
"""
from __future__ import annotations

import json
import urllib.error
import urllib.request
from collections.abc import Callable

from asistente.brain.claude_client import DEFAULT_SYSTEM


def build_payload(model: str, text: str, system: str = DEFAULT_SYSTEM,
                  stream: bool = False) -> dict:
    """Cuerpo del POST a /api/chat. Función pura → testeable sin servidor."""
    return {
        "model": model,
        "stream": stream,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": text},
        ],
    }


def parse_response(raw: str) -> str:
    """Extrae el texto de la respuesta JSON de /api/chat (no streaming)."""
    obj = json.loads(raw)
    return (obj.get("message", {}).get("content") or "").strip()


class OllamaBrain:
    """LLM local vía Ollama. Interfaz compatible con WarmClaude."""

    def __init__(self, model: str = "qwen3.5:9b",
                 host: str = "http://127.0.0.1:11434",
                 system: str = DEFAULT_SYSTEM, timeout: float = 60.0) -> None:
        self.model = model
        self.host = host.rstrip("/")
        self.system = system
        self.timeout = timeout

    def ask(self, text: str, on_delta: Callable[[str], None] | None = None) -> str:
        data = json.dumps(build_payload(self.model, text, self.system)).encode("utf-8")
        req = urllib.request.Request(
            f"{self.host}/api/chat", data=data,
            headers={"Content-Type": "application/json"},
        )
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                out = parse_response(resp.read().decode("utf-8"))
        except urllib.error.URLError as e:
            raise RuntimeError(f"No pude hablar con Ollama en {self.host}: {e}") from e
        if on_delta and out:
            on_delta(out)
        return out

    def prewarm(self) -> None:
        """Carga el modelo en VRAM con una llamada dummy (la 1ª siempre tarda más)."""
        try:
            self.ask("hola")
        except Exception:  # noqa: BLE001
            pass

    def stop(self) -> None:
        # Ollama es un servidor aparte; no hay proceso propio que matar.
        pass
