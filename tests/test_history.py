from asistente.ui.history import format_answer_entry, append_history


def test_format_incluye_hora_y_texto():
    e = format_answer_entry("  Hola mundo  ", "09:57")
    assert "09:57" in e
    assert e.endswith("Hola mundo")


def test_append_en_vacio_es_solo_la_entrada():
    out = append_history("", "primera", "09:00")
    assert "primera" in out
    assert out.count("─") > 0


def test_append_acumula_no_pisa():
    h1 = append_history("", "primera", "09:00")
    h2 = append_history(h1, "segunda", "09:05")
    # se conservan ambas, en orden, separadas
    assert "primera" in h2 and "segunda" in h2
    assert h2.index("primera") < h2.index("segunda")
    assert "\n\n" in h2
