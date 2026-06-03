import json
import pytest
from asistente.events import TranscriptFinal, Suggestion, parse_client_event, AskCommand


def test_transcript_final_serializa_con_tipo():
    ev = TranscriptFinal(text="hola mundo", ts=12.5)
    data = json.loads(ev.model_dump_json())
    assert data["type"] == "transcript.final"
    assert data["text"] == "hola mundo"
    assert data["ts"] == 12.5


def test_suggestion_serializa():
    ev = Suggestion(text="Diría que vamos al 80%.", ready=True)
    data = json.loads(ev.model_dump_json())
    assert data["type"] == "suggestion"
    assert data["ready"] is True


def test_parse_client_event_ask():
    cmd = parse_client_event('{"type": "ask", "text": "resume esto"}')
    assert isinstance(cmd, AskCommand)
    assert cmd.text == "resume esto"


def test_parse_client_event_tipo_desconocido():
    with pytest.raises(ValueError):
        parse_client_event('{"type": "loquesea"}')


def test_parse_client_event_json_invalido():
    with pytest.raises(json.JSONDecodeError):
        parse_client_event('no es json {')
