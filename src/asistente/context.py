"""Contexto de sesión en 3 capas, para que el copiloto no pierda el enfoque en
llamadas largas que saltan de tema.

- **Briefing** (durable): proyecto, participantes, objetivos, términos. Editable en la
  UI y/o cargado de un archivo/ruta al inicio.
- **Resumen acumulativo**: se actualiza cada N finales y reemplaza al anterior (no crece).
- **Ventana rodante**: las últimas frases, para inmediatez.

`compose()` arma el contexto con prioridad briefing > resumen > ventana, recortado a un
presupuesto de caracteres para no inflar tokens. Las funciones puras se testean sin GPU.
"""
from __future__ import annotations

import threading
from collections import deque
from pathlib import Path


def compose_context(briefing: str, summary: str, window_lines: list[str],
                    max_chars: int = 2000) -> str:
    """Ensambla las 3 capas. Briefing y resumen (cortos por diseño) van completos;
    la ventana se recorta por el FINAL (conserva lo más reciente) con lo que quede
    del presupuesto."""
    head_parts: list[str] = []
    if briefing.strip():
        head_parts.append("[BRIEFING]\n" + briefing.strip())
    if summary.strip():
        head_parts.append("[RESUMEN HASTA AHORA]\n" + summary.strip())
    head = "\n\n".join(head_parts)

    win = ""
    if window_lines:
        remaining = max_chars - len(head) - 2  # 2 por el separador
        full = "[ÚLTIMO]\n" + "\n".join(s for s in window_lines if s.strip())
        if remaining > 0:
            win = full if len(full) <= remaining else full[-remaining:]
    if head and win:
        return head + "\n\n" + win
    return head or win


def build_summary_prompt(prev_summary: str, new_lines: list[str]) -> str:
    """Prompt para actualizar el resumen acumulativo reemplazando al anterior."""
    nuevas = "\n".join(new_lines)
    base = f"Resumen previo de la reunión:\n{prev_summary}\n\n" if prev_summary.strip() else ""
    return (
        f"{base}Frases nuevas de la reunión:\n{nuevas}\n\n"
        f"Actualiza el resumen ACUMULATIVO de la reunión en 3-5 viñetas breves que "
        f"capturen los temas tratados y las decisiones (no solo lo último). "
        f"Devuelve SOLO el resumen, sin preámbulo."
    )


def load_briefing_source(path: str, max_chars: int = 6000) -> str:
    """Lee un archivo de texto o concatena los .txt/.md de un directorio (hasta un tope)
    para usarlo como material del briefing. Devuelve "" si no existe o no hay texto."""
    p = Path(path).expanduser()
    if not p.exists():
        return ""
    texts: list[str] = []
    if p.is_dir():
        for f in sorted(p.rglob("*")):
            if f.suffix.lower() in {".txt", ".md", ".rst"} and f.is_file():
                try:
                    texts.append(f"# {f.name}\n" + f.read_text(errors="ignore"))
                except OSError:
                    continue
            if sum(len(t) for t in texts) >= max_chars:
                break
    else:
        try:
            texts.append(p.read_text(errors="ignore"))
        except OSError:
            return ""
    out = "\n\n".join(texts).strip()
    return out[:max_chars]


class SessionContext:
    """Contexto compartido entre el copiloto, la sugerencia proactiva y el 'preguntar'.

    Thread-safe (lo escribe el hilo de audio vía add_final y lo lee el copiloto).
    """

    def __init__(self, window: int = 12, summary_every: int = 8) -> None:
        self.briefing = ""
        self.running_summary = ""
        self.window: deque[str] = deque(maxlen=window)
        self.summary_every = summary_every
        self._total = 0
        self._since_summary: list[str] = []
        self._lock = threading.Lock()

    @property
    def total(self) -> int:
        """Total monotónico de finales agregados (no se topa como len(deque))."""
        return self._total

    def add_final(self, text: str) -> None:
        t = (text or "").strip()
        if not t:
            return
        with self._lock:
            self.window.append(t)
            self._since_summary.append(t)
            self._total += 1

    def set_briefing(self, text: str) -> None:
        self.briefing = (text or "").strip()

    def append_briefing(self, text: str) -> None:
        extra = (text or "").strip()
        if not extra:
            return
        self.briefing = (self.briefing + "\n\n" + extra).strip() if self.briefing else extra

    def set_summary(self, text: str) -> None:
        if text and text.strip():
            self.running_summary = text.strip()

    def needs_summary(self) -> bool:
        return len(self._since_summary) >= self.summary_every

    def take_new_for_summary(self) -> list[str]:
        with self._lock:
            lines = self._since_summary
            self._since_summary = []
        return lines

    def compose(self, max_chars: int = 2000) -> str:
        with self._lock:
            win = list(self.window)
        return compose_context(self.briefing, self.running_summary, win, max_chars)
