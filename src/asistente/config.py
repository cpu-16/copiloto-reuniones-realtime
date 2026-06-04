"""Carga de config.toml a objetos tipados."""
from __future__ import annotations

import tomllib
from pathlib import Path

from pydantic import BaseModel


class UserCfg(BaseModel):
    names: list[str] = []
    reply_language: str = "es"
    # Quién eres y qué buscas en las reuniones; la IA adapta sus sugerencias.
    role: str = "un participante de la reunión"


class CopilotCfg(BaseModel):
    enabled: bool = True
    interval_s: float = 15.0   # cada cuánto el copiloto analiza el contexto


class AudioCfg(BaseModel):
    target: str = ""
    sample_rate: int = 16000


class WhisperCfg(BaseModel):
    model: str = "turbo"
    realtime_model: str = "small"   # modelo de los parciales (tiny<base<small)
    realtime_pause: float = 0.2     # cada cuántos s re-transcribe (más alto = menos GPU)
    enable_realtime: bool = True    # False = solo finales (mínima GPU, sin texto fluido)
    compute_type: str = "float16"
    language: str = "es"


class ClaudeCfg(BaseModel):
    model: str = "haiku"


class ServerCfg(BaseModel):
    host: str = "127.0.0.1"
    port: int = 8765
    token: str = "cambia-este-token"


class Config(BaseModel):
    # Motor de transcripción: "whisper" (.venv) o "parakeet" (.venv-parakeet, más liviano).
    engine: str = "whisper"
    user: UserCfg = UserCfg()
    audio: AudioCfg = AudioCfg()
    whisper: WhisperCfg = WhisperCfg()
    claude: ClaudeCfg = ClaudeCfg()
    copilot: CopilotCfg = CopilotCfg()
    server: ServerCfg = ServerCfg()


def load_config(path: Path | str = "config.toml") -> Config:
    with open(path, "rb") as f:
        data = tomllib.load(f)
    return Config(**data)
