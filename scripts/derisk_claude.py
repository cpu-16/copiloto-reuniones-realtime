"""De-risk de Claude: mide latencia de `claude -p` descafeinado.
Modo frío: una invocación nueva por pregunta.
Modo caliente: un proceso persistente alimentado por stream-json.
Uso: python scripts/derisk_claude.py
"""
import json
import subprocess
import time

SYSTEM = (
    "Eres un copiloto de reuniones. Dado el contexto de una conversación, responde SIEMPRE "
    "con una sugerencia de respuesta corta (1-2 frases) en español que el usuario podría decir. "
    "Nunca pidas aclaración. Nunca expliques. Solo la respuesta sugerida."
)

CONTEXT = (
    "En la reunión preguntan: '¿Cuál es el estado del proyecto de migración a la nube?'"
)


def cold_call(context: str) -> tuple[str, float]:
    cmd = [
        "claude", "-p",
        "--model", "haiku",
        "--setting-sources", "",        # sin hooks/settings de usuario ni proyecto
        "--strict-mcp-config",          # sin --mcp-config => ignora todos los MCP
        "--allowed-tools", "",          # sin herramientas
        "--system-prompt", SYSTEM,
        "--exclude-dynamic-system-prompt-sections",
        "--max-turns", "1",
        context,
    ]
    t0 = time.perf_counter()
    out = subprocess.run(cmd, capture_output=True, text=True)
    dt = time.perf_counter() - t0
    return out.stdout.strip() or out.stderr.strip(), dt


class WarmClaude:
    """Proceso `claude -p` persistente alimentado vía stream-json por stdin.

    Estructura de eventos REAL descubierta en v2.1.162:
      - Deltas de texto:
          {"type":"stream_event","event":{"type":"content_block_delta",
           "index":N,"delta":{"type":"text_delta","text":"..."}}}
        OJO: Haiku hace "extended thinking" por defecto y emite ANTES
        deltas de tipo "thinking_delta" en el mismo content_block_delta.
        Hay que filtrar SOLO delta.type == "text_delta".
      - Fin de respuesta:
          {"type":"result","subtype":"success",...,"result":"<texto completo>"}
        El evento `result` es el terminador limpio y trae el texto final
        en el campo `result`.
    """

    def __init__(self) -> None:
        cmd = [
            "claude", "-p", "--model", "haiku",
            "--setting-sources", "", "--strict-mcp-config",
            "--allowed-tools", "", "--system-prompt", SYSTEM,
            "--exclude-dynamic-system-prompt-sections",
            "--input-format", "stream-json",
            "--output-format", "stream-json",
            "--include-partial-messages", "--verbose",
        ]
        self.proc = subprocess.Popen(
            cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            text=True, bufsize=1,
        )

    def ask(self, text: str) -> tuple[str, float, float]:
        msg = {
            "type": "user",
            "message": {"role": "user", "content": [{"type": "text", "text": text}]},
        }
        t0 = time.perf_counter()
        self.proc.stdin.write(json.dumps(msg) + "\n")
        self.proc.stdin.flush()
        ttft = None
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
            # Delta incremental de TEXTO (ignorar thinking_delta).
            if etype == "stream_event":
                inner = ev.get("event", {})
                if inner.get("type") == "content_block_delta":
                    delta = inner.get("delta", {})
                    if delta.get("type") == "text_delta":
                        if ttft is None:
                            ttft = time.perf_counter() - t0
                        chunks.append(delta.get("text", ""))
            # Fin de respuesta: trae el texto completo en `result`.
            elif etype == "result":
                final = ev.get("result", "")
                if final and not chunks:
                    chunks.append(final)
                break
        total = time.perf_counter() - t0
        return "".join(chunks).strip(), (ttft or total), total

    def close(self) -> None:
        try:
            if self.proc.stdin:
                self.proc.stdin.close()
        except Exception:
            pass
        try:
            self.proc.wait(timeout=5)
        except Exception:
            self.proc.kill()


def warm_demo() -> None:
    print("\n=== Claude CALIENTE (proceso persistente) ===")
    client = WarmClaude()
    try:
        for i in range(3):
            text, ttft, total = client.ask(CONTEXT)
            print(f"[{i + 1}] TTFT={ttft:.2f}s total={total:.2f}s -> {text[:140]}")
    finally:
        client.close()


def main() -> None:
    print("=== Claude FRÍO (descafeinado) ===")
    for i in range(3):
        text, dt = cold_call(CONTEXT)
        print(f"[{i + 1}] {dt:.2f}s -> {text[:160]}")
    warm_demo()


if __name__ == "__main__":
    main()
