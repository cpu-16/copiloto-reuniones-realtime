import json
from asistente.brain.claude_client import build_user_message, build_cmd


def test_build_user_message():
    msg = build_user_message("hola")
    data = json.loads(msg)
    assert data["type"] == "user"
    assert data["message"]["content"][0]["text"] == "hola"


def test_build_cmd_descafeinado():
    cmd = build_cmd(model="haiku", system="SP")
    # Flags existentes
    assert "--strict-mcp-config" in cmd
    assert "--setting-sources" in cmd
    i = cmd.index("--allowed-tools")
    assert cmd[i + 1] == ""
    assert "--model" in cmd and cmd[cmd.index("--model") + 1] == "haiku"
    # Flags adicionales requeridos
    assert "--exclude-dynamic-system-prompt-sections" in cmd
    assert "--include-partial-messages" in cmd
    assert "--verbose" in cmd
    # --input-format stream-json
    assert "--input-format" in cmd
    assert cmd[cmd.index("--input-format") + 1] == "stream-json"
    # --output-format stream-json
    assert "--output-format" in cmd
    assert cmd[cmd.index("--output-format") + 1] == "stream-json"
    # --system-prompt seguido del system string dado
    assert "--system-prompt" in cmd
    assert cmd[cmd.index("--system-prompt") + 1] == "SP"
