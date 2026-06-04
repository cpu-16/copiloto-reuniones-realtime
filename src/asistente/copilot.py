"""Copiloto continuo: arma el prompt para Claude y parsea su respuesta en secciones.

Una sola llamada a Claude cubre: resumen de lo que se habla, ideas de qué decir/preguntar,
un borrador de respuesta por si te preguntan de golpe, y una alerta de decisión/tarea.
"""
from __future__ import annotations


def build_copilot_prompt(role: str, names: list[str], context: str) -> str:
    yo = names[0] if names else "el usuario"
    return (
        f"Eres el copiloto en tiempo real de {yo}, que es {role}. "
        f"Esta es la transcripción reciente de una reunión:\n\n{context}\n\n"
        f"Responde EXACTAMENTE en este formato, en español, breve y sin nada más:\n"
        f"RESUMEN: <una línea de qué se está hablando>\n"
        f"IDEAS: <1-2 cosas concretas que {yo} podría aportar, decir o preguntar ahora>\n"
        f"BORRADOR: <si a {yo} le preguntaran algo ahora, una respuesta corta que daría>\n"
        f"ALERTA: <una decisión tomada o una tarea asignada a {yo}; si no hay, escribe NINGUNA>"
    )


_NONE = {"ninguna", "ninguno", "n/a", "na", "-", "none", ""}


def parse_copilot(text: str) -> dict:
    out = {"summary": "", "ideas": "", "draft": "", "alert": ""}
    keys = {"resumen": "summary", "ideas": "ideas", "borrador": "draft", "alerta": "alert"}
    for line in text.splitlines():
        line = line.strip().lstrip("-*•").strip()
        if ":" not in line:
            continue
        head, _, val = line.partition(":")
        key = keys.get(head.strip().lower())
        if key:
            out[key] = val.strip()
    if out["alert"].lower() in _NONE:
        out["alert"] = ""
    return out
