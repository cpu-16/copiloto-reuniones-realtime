from pathlib import Path
from asistente.config import load_config


def test_load_config(tmp_path: Path):
    p = tmp_path / "config.toml"
    p.write_text(
        '[user]\nnames=["Rafa"]\nreply_language="es"\n'
        '[audio]\ntarget="mon.1"\nsample_rate=16000\n'
        '[whisper]\nmodel="turbo"\ncompute_type="float16"\nlanguage="es"\n'
        '[claude]\nmodel="haiku"\n'
        '[server]\nhost="127.0.0.1"\nport=8765\ntoken="t0k"\n'
    )
    cfg = load_config(p)
    assert cfg.user.names == ["Rafa"]
    assert cfg.audio.target == "mon.1"
    assert cfg.server.token == "t0k"
    assert cfg.whisper.model == "turbo"
