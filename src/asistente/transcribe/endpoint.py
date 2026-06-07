"""Endpointing para ASR en streaming acumulativo (Nemotron cache-aware).

El modelo en streaming devuelve la transcripción ACUMULADA de todo el stream. Para
alimentar el contexto y disparar la detección de pregunta hay que segmentarla en
frases (finales) y exponer el resto como parcial. Función pura → testeable.
"""
from __future__ import annotations

import re

# Una "frase": texto hasta (incluyendo) uno o más signos de cierre . ? !
_SENTENCE = re.compile(r"[^.?!]*[.?!]+", re.DOTALL)


def segment_finals(full_text: str, emitted: int) -> tuple[list[str], int, str]:
    """Dada la transcripción acumulada `full_text` y cuántos caracteres ya se
    finalizaron (`emitted`), devuelve:
      - finals: frases nuevas completas (terminadas en puntuación),
      - new_emitted: nuevo offset de lo finalizado,
      - partial: el resto sin cerrar (texto en curso).
    """
    pending = full_text[emitted:]
    finals: list[str] = []
    consumed = 0
    for m in _SENTENCE.finditer(pending):
        seg = m.group().strip()
        if seg:
            finals.append(seg)
        consumed = m.end()
    new_emitted = emitted + consumed
    partial = full_text[new_emitted:].strip()
    return finals, new_emitted, partial
