"""Corrección post-ASR por similitud contra un glosario de términos del proyecto.

Sin LLM ni GPU: para cada palabra, si se parece mucho a un término del glosario
(nombres propios, jerga técnica) se sustituye. Complementa/respalda al phrase boosting
nativo. Función pura → testeable.
"""
from __future__ import annotations

from difflib import SequenceMatcher

_PUNCT = ".,;:!?¿¡\"')("


def correct_terms(text: str, glossary: list[str], threshold: float = 0.82) -> str:
    """Sustituye palabras casi-iguales a un término del glosario. Conserva la
    puntuación pegada a la palabra. `threshold` es el ratio mínimo de similitud."""
    if not glossary or not text:
        return text
    out: list[str] = []
    for w in text.split():
        core = w.strip(_PUNCT)
        if not core:
            out.append(w)
            continue
        best, score = "", 0.0
        for term in glossary:
            if " " in term:   # los términos multi-palabra no se casan contra una sola
                continue
            r = SequenceMatcher(None, core.lower(), term.lower()).ratio()
            if r > score:
                best, score = term, r
        if best and score >= threshold and core.lower() != best.lower():
            out.append(w.replace(core, best, 1))
        else:
            out.append(w)
    return " ".join(out)
