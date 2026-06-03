"""Cerebro: proceso `claude -p` caliente (stream-json), descafeinado, modelo Haiku.

El parseo de eventos refleja el formato real del CLI v2.1.162 descubierto en de-risk:
Haiku emite `thinking_delta` antes del texto; solo se recogen los `text_delta`.
El evento `result` cierra la respuesta y trae el texto completo.
"""
from __future__ import annotations

import json
import subprocess
from collections.abc import Callable

DEFAULT_SYSTEM = (
    "Eres un copiloto de reuniones. Dado el contexto de la conversación, responde SIEMPRE "
    "con una sugerencia de respuesta corta (1-2 frases) en español que el usuario podría "
    "decir. Nunca pidas aclaración. Nunca expliques. Solo la respuesta sugerida."
)


def build_cmd(model: str = "haiku", system: str = DEFAULT_SYSTEM) -> list[str]:
    return [
        "claude", "-p",
        "--model", model,
        "--setting-sources", "",
        "--strict-mcp-config",
        "--allowed-tools", "",
        "--system-prompt", system,
        "--exclude-dynamic-system-prompt-sections",
        "--input-format", "stream-json",
        "--output-format", "stream-json",
        "--include-partial-messages",
        "--verbose",
    ]


def build_user_message(text: str) -> str:
    return json.dumps({
        "type": "user",
        "message": {"role": "user", "content": [{"type": "text", "text": text}]},
    })


class WarmClaude:
    """Mantiene un proceso claude -p vivo y responde con streaming por callback."""

    def __init__(self, model: str = "haiku", system: str = DEFAULT_SYSTEM) -> None:
        self.proc = subprocess.Popen(
            build_cmd(model, system),
            stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            text=True, bufsize=1,
        )

    def ask(self, text: str, on_delta: Callable[[str], None] | None = None) -> str:
        if not (self.proc.stdin and self.proc.stdout):
            raise RuntimeError("El proceso de Claude no tiene stdin/stdout disponibles.")
        self.proc.stdin.write(build_user_message(text) + "\n")
        self.proc.stdin.flush()
        chunks: list[str] = []
        for line in self.proc.stdout:
            line = line.strip()
            if not line:
                continue
            try:
                ev = json.loads(line)
            except json.JSONDecodeError:
                continue
            etype = ev.get("type")
            if etype == "stream_event":
                inner = ev.get("event", {})
                if inner.get("type") == "content_block_delta":
                    delta = inner.get("delta", {})
                    if delta.get("type") == "text_delta":  # ignora thinking_delta
                        piece = delta.get("text", "")
                        chunks.append(piece)
                        if on_delta:
                            on_delta(piece)
            elif etype == "result":
                final = ev.get("result", "")
                if final and not chunks:
                    chunks.append(final)
                break
        if not chunks and self.proc.poll() is not None:
            raise RuntimeError("El proceso de Claude terminó inesperadamente.")
        return "".join(chunks).strip()

    def prewarm(self) -> None:
        """Primera llamada dummy para calentar el prompt cache (~5s) y dejar las
        siguientes en <3s. Llamar una vez al arrancar."""
        self.ask("hola")

    def stop(self) -> None:
        if self.proc.poll() is None:
            self.proc.terminate()
            self.proc.wait()
