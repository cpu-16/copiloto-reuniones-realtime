"""Contrato de eventos del WebSocket entre orquestador y UIs.
Servidor -> UI: TranscriptPartial, TranscriptFinal, Suggestion, Status.
UI -> Servidor: AskCommand, ClearCommand.
"""
from __future__ import annotations

import json
from typing import Literal, Union

from pydantic import BaseModel


class TranscriptPartial(BaseModel):
    type: Literal["transcript.partial"] = "transcript.partial"
    text: str
    ts: float  # segundos desde el inicio de la captura


class TranscriptFinal(BaseModel):
    type: Literal["transcript.final"] = "transcript.final"
    text: str
    ts: float  # segundos desde el inicio de la captura


class Suggestion(BaseModel):
    type: Literal["suggestion"] = "suggestion"
    text: str
    ready: bool = False  # True cuando se detectó pregunta directa (Fase 2)


class Answer(BaseModel):
    """Respuesta a pedido (botones/cuadro). Va al panel lateral persistente, no a la
    tarjeta de sugerencia proactiva (que el copiloto sobrescribe). `tab` enruta a la
    pestaña: ideas|resumen|pregunto|respondo|libre."""
    type: Literal["answer"] = "answer"
    tab: str = "libre"
    text: str
    ready: bool = True


class Insight(BaseModel):
    """Copiloto continuo: lo que la IA infiere del contexto en tiempo real."""
    type: Literal["insight"] = "insight"
    summary: str = ""     # de qué se está hablando
    ideas: str = ""       # 1-2 cosas que el usuario podría decir/preguntar
    alert: str = ""       # decisión o tarea detectada (vacío si no hay)


class Toggle(BaseModel):
    """Pide a la UI alternar visibilidad (atajo global mostrar/ocultar)."""
    type: Literal["toggle"] = "toggle"


class Ghost(BaseModel):
    """Pide a la UI alternar el modo fantasma: la ventana se vuelve atravesable
    (click-through) y semitransparente. Atajo global (curl /ghost)."""
    type: Literal["ghost"] = "ghost"


class Status(BaseModel):
    type: Literal["status"] = "status"
    state: str           # "capturando", "pensando", "error", ...
    detail: str = ""


class AskCommand(BaseModel):
    type: Literal["ask"] = "ask"
    text: str
    tab: str = ""  # pestaña destino del panel (vacío = "libre"); el server enruta la Answer


class ClearCommand(BaseModel):
    type: Literal["clear"] = "clear"


class CaptureCommand(BaseModel):
    """Pausa/reanuda la captura. paused=True descarta parciales/finales (no transcribe,
    no entra al contexto, no va a Claude); pw-record y el transcriptor siguen vivos."""
    type: Literal["capture"] = "capture"
    paused: bool


class BriefingSet(BaseModel):
    """UI -> servidor: fija el briefing durable de la sesión (capa 1 del contexto)."""
    type: Literal["briefing.set"] = "briefing.set"
    text: str


class BriefingState(BaseModel):
    """Servidor -> UI: el briefing actual (eco tras set o tras ingestión inicial),
    para sincronizar el contenido entre UIs."""
    type: Literal["briefing.state"] = "briefing.state"
    text: str


ClientEvent = Union[AskCommand, ClearCommand, CaptureCommand, BriefingSet]


def parse_client_event(raw: str) -> ClientEvent:
    # Si la unión crece a varios comandos, considera un discriminated union de pydantic.
    data = json.loads(raw)
    kind = data.get("type")
    if kind == "ask":
        return AskCommand(**data)
    if kind == "clear":
        return ClearCommand(**data)
    if kind == "capture":
        return CaptureCommand(**data)
    if kind == "briefing.set":
        return BriefingSet(**data)
    raise ValueError(f"Evento de cliente desconocido: {kind!r}")
