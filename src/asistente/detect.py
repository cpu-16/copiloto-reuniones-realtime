"""Detección heurística de "¿me están preguntando a MÍ?" sobre la transcripción.

No es perfecto (es una heurística barata); la sugerencia que dispara es no intrusiva,
así que un falso positivo ocasional solo muestra una sugerencia que puedes ignorar.
Regla: el texto parece una PREGUNTA y además parece DIRIGIDA a ti (menciona tu nombre
o usa segunda persona).
"""
from __future__ import annotations

_QUESTION_WORDS = (
    "qué", "que", "cómo", "como", "cuándo", "cuando", "cuál", "cual",
    "por qué", "porqué", "dónde", "donde", "quién", "quien",
    "puedes", "podrías", "podrias", "opinas", "piensas", "crees",
    "cuéntanos", "cuentanos", "explica", "explícanos", "explicanos",
)
_SECOND_PERSON = (
    " tú ", " tu ", " usted ", " ustedes ", " te ", " ti ", " contigo ",
    " opinas", " piensas", " crees", " puedes", " podrías", " dirías", " harías",
)


def _norm(s: str) -> str:
    return s.lower().strip()


def looks_like_question(text: str) -> bool:
    t = _norm(text)
    if not t:
        return False
    if "?" in t or "¿" in t:
        return True
    padded = f" {t} "
    return any(t.startswith(w + " ") or f" {w} " in padded for w in _QUESTION_WORDS)


def directed_at_me(text: str, names: list[str]) -> bool:
    padded = f" {_norm(text)} "
    if any(name and _norm(name) in padded for name in names):
        return True
    return any(sp in padded for sp in _SECOND_PERSON)


def is_question_for_me(text: str, names: list[str]) -> bool:
    """True si el texto parece una pregunta dirigida al usuario."""
    return looks_like_question(text) and directed_at_me(text, names)
