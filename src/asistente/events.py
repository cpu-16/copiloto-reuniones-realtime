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


class Status(BaseModel):
    type: Literal["status"] = "status"
    state: str           # "capturando", "pensando", "error", ...
    detail: str = ""


class AskCommand(BaseModel):
    type: Literal["ask"] = "ask"
    text: str


class ClearCommand(BaseModel):
    type: Literal["clear"] = "clear"


ClientEvent = Union[AskCommand, ClearCommand]


def parse_client_event(raw: str) -> ClientEvent:
    # Si la unión crece a varios comandos, considera un discriminated union de pydantic.
    data = json.loads(raw)
    kind = data.get("type")
    if kind == "ask":
        return AskCommand(**data)
    if kind == "clear":
        return ClearCommand(**data)
    raise ValueError(f"Evento de cliente desconocido: {kind!r}")
