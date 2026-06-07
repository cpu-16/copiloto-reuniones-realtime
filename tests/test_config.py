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
    # defaults del bloque [parakeet] aunque no esté en el toml
    assert cfg.parakeet.silence_rms == 0.0
    assert cfg.parakeet.auto_calibrate is True


def test_parakeet_overrides(tmp_path: Path):
    p = tmp_path / "config.toml"
    p.write_text(
        '[server]\ntoken="t"\n'
        '[parakeet]\nsilence_rms=420\nauto_calibrate=false\n'
    )
    cfg = load_config(p)
    assert cfg.parakeet.silence_rms == 420
    assert cfg.parakeet.auto_calibrate is False


def test_nemotron_y_asr_defaults_y_overrides(tmp_path: Path):
    p = tmp_path / "config.toml"
    p.write_text(
        'engine="nemotron"\n'
        '[server]\ntoken="t"\n'
        '[nemotron]\natt_context_size=[56,6]\ntarget_lang="auto"\n'
        '[asr]\nglossary=["Kubernetes","Rafael Valdés"]\n'
    )
    cfg = load_config(p)
    assert cfg.engine == "nemotron"
    assert cfg.nemotron.att_context_size == [56, 6]
    assert cfg.nemotron.target_lang == "auto"
    assert "Kubernetes" in cfg.asr.glossary
    assert cfg.asr.correct_enabled is True   # default
    # defaults del modelo nemotron
    assert "nemotron" in cfg.nemotron.model
