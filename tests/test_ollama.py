"""Tests de los helpers puros del cerebro Ollama (sin servidor)."""
from asistente.brain.ollama_client import build_payload, parse_response, OllamaBrain


def test_build_payload_estructura():
    p = build_payload("gemma4:e2b", "¿qué digo?", system="sé breve")
    assert p["model"] == "gemma4:e2b"
    assert p["stream"] is False
    assert p["messages"][0] == {"role": "system", "content": "sé breve"}
    assert p["messages"][1] == {"role": "user", "content": "¿qué digo?"}


def test_parse_response_extrae_contenido():
    raw = '{"message": {"role": "assistant", "content": "  Diría que sí.  "}, "done": true}'
    assert parse_response(raw) == "Diría que sí."


def test_parse_response_vacio():
    assert parse_response('{"message": {}}') == ""


def test_ollama_brain_interfaz_compatible():
    # mismos métodos que WarmClaude (duck typing): ask / prewarm / stop
    b = OllamaBrain(model="x", host="http://127.0.0.1:11434/")
    assert b.host == "http://127.0.0.1:11434"   # sin barra final
    assert hasattr(b, "ask") and hasattr(b, "prewarm") and hasattr(b, "stop")
