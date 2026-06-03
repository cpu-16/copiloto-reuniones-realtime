"""Carga de config.toml a objetos tipados."""
from __future__ import annotations

import tomllib
from pathlib import Path

from pydantic import BaseModel


class UserCfg(BaseModel):
    names: list[str] = []
    reply_language: str = "es"


class AudioCfg(BaseModel):
    target: str = ""
    sample_rate: int = 16000


class WhisperCfg(BaseModel):
    model: str = "turbo"
    compute_type: str = "float16"
    language: str = "es"


class ClaudeCfg(BaseModel):
    model: str = "haiku"


class ServerCfg(BaseModel):
    host: str = "127.0.0.1"
    port: int = 8765
    token: str = "cambia-este-token"


class Config(BaseModel):
    user: UserCfg = UserCfg()
    audio: AudioCfg = AudioCfg()
    whisper: WhisperCfg = WhisperCfg()
    claude: ClaudeCfg = ClaudeCfg()
    server: ServerCfg = ServerCfg()


def load_config(path: Path | str = "config.toml") -> Config:
    with open(path, "rb") as f:
        data = tomllib.load(f)
    return Config(**data)
