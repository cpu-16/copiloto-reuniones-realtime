"""Formato puro de las entradas del historial del panel de respuestas.

Sin dependencias de Qt para poder testearlo sin entorno gráfico. La UI (`native.py`)
añade cada respuesta nueva debajo de las anteriores en vez de pisarlas.
"""
from __future__ import annotations


def format_answer_entry(text: str, when: str) -> str:
    """Una entrada del historial: separador con hora + el texto. `when` es 'HH:MM'."""
    return f"── {when} ─────────────\n{text.strip()}"


def append_history(existing: str, text: str, when: str) -> str:
    """Añade una entrada al historial existente, separada por una línea en blanco.
    Si no había nada, devuelve solo la entrada nueva."""
    entry = format_answer_entry(text, when)
    base = existing.rstrip()
    return f"{base}\n\n{entry}" if base else entry
