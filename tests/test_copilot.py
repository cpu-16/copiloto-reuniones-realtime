from asistente.copilot import build_copilot_prompt, parse_copilot


def test_prompt_incluye_rol_y_contexto():
    p = build_copilot_prompt("un dev backend", ["Rafa"], "Se habló de Kubernetes.")
    assert "Rafa" in p and "dev backend" in p and "Kubernetes" in p


def test_parse_secciones():
    txt = (
        "RESUMEN: Hablan de la migración a la nube.\n"
        "IDEAS: Podrías proponer un plan por fases.\n"
        "BORRADOR: Vamos al 70%, sin bloqueos.\n"
        "ALERTA: A Rafa le toca el informe."
    )
    out = parse_copilot(txt)
    assert out["summary"].startswith("Hablan")
    assert "fases" in out["ideas"]
    assert out["draft"].startswith("Vamos")
    assert "informe" in out["alert"]


def test_parse_alerta_ninguna_queda_vacia():
    out = parse_copilot("RESUMEN: x\nIDEAS: y\nBORRADOR: z\nALERTA: NINGUNA")
    assert out["alert"] == ""


def test_parse_tolera_vinetas_y_basura():
    out = parse_copilot("- RESUMEN: algo\nlinea suelta\n* IDEAS: otra")
    assert out["summary"] == "algo"
    assert out["ideas"] == "otra"
