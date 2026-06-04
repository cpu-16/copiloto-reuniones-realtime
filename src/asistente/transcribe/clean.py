"""Filtro de alucinaciones típicas de Whisper sobre silencio/música.

Whisper, entrenado con mucho YouTube, "inventa" frases como 'Thanks for watching',
'¡Suscríbete!' o 'You' cuando el audio es silencio o música de fondo. Descartamos
solo coincidencias EXACTAS de frases-basura conocidas, para no tragarnos respuestas
cortas legítimas (un 'sí'/'no' real no se filtra).
"""
from __future__ import annotations

import re
import unicodedata

_JUNK = {
    "you", "thank you", "thank you very much", "thanks for watching",
    "thank you for watching", "please subscribe", "subscribe",
    "like and subscribe", "see you next time", "see you in the next video",
    "suscribete", "gracias por ver", "gracias por ver el video",
    "gracias por ver el vídeo", "no olvides suscribirte",
    "subtitulos realizados por la comunidad de amara org",
    "subtítulos realizados por la comunidad de amara.org",
    "subtitles by the amara org community",
}


def _norm(t: str) -> str:
    t = t.lower().strip()
    # quita tildes/acentos para que 'suscríbete' == 'suscribete'
    t = "".join(c for c in unicodedata.normalize("NFD", t)
                if unicodedata.category(c) != "Mn")
    t = re.sub(r"[¡!¿?.,…\"'’\-]+", " ", t)
    t = re.sub(r"\s+", " ", t).strip()
    return t


def is_hallucination(text: str) -> bool:
    n = _norm(text)
    if not n:
        return True
    return n in _JUNK
