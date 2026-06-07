from asistente.context import (
    SessionContext, compose_context, build_summary_prompt, load_briefing_source,
)


def test_compose_orden_y_etiquetas():
    out = compose_context("Proyecto X", "Se decidió A", ["hola", "que tal"])
    assert out.index("[BRIEFING]") < out.index("[RESUMEN HASTA AHORA]") < out.index("[ÚLTIMO]")
    assert "Proyecto X" in out and "Se decidió A" in out and "que tal" in out


def test_compose_omite_capas_vacias():
    out = compose_context("", "", ["solo ventana"])
    assert "[BRIEFING]" not in out and "[RESUMEN" not in out
    assert "[ÚLTIMO]" in out and "solo ventana" in out


def test_compose_recorta_ventana_por_el_final():
    briefing = "B" * 50
    win = [f"linea {i}" for i in range(200)]
    out = compose_context(briefing, "", win, max_chars=200)
    assert len(out) <= 200
    assert "[BRIEFING]" in out          # el briefing se conserva
    assert "linea 199" in out           # conserva lo más reciente
    assert "linea 0" not in out         # recorta lo viejo


def test_add_final_total_monotonico_y_ventana_topada():
    ctx = SessionContext(window=3, summary_every=8)
    for i in range(10):
        ctx.add_final(f"f{i}")
    assert ctx.total == 10                 # no se topa como len(deque)
    assert list(ctx.window) == ["f7", "f8", "f9"]


def test_add_final_ignora_vacios():
    ctx = SessionContext()
    ctx.add_final("   ")
    ctx.add_final("")
    assert ctx.total == 0


def test_resumen_se_dispara_y_se_vacia():
    ctx = SessionContext(window=12, summary_every=3)
    ctx.add_final("a"); ctx.add_final("b")
    assert not ctx.needs_summary()
    ctx.add_final("c")
    assert ctx.needs_summary()
    nuevas = ctx.take_new_for_summary()
    assert nuevas == ["a", "b", "c"]
    assert not ctx.needs_summary()         # se vació


def test_compose_incluye_briefing_y_resumen_seteados():
    ctx = SessionContext()
    ctx.set_briefing("Reunión sobre migración a la nube")
    ctx.set_summary("- Tema 1\n- Tema 2")
    ctx.add_final("última frase")
    out = ctx.compose()
    assert "migración a la nube" in out and "Tema 1" in out and "última frase" in out


def test_append_briefing_concatena():
    ctx = SessionContext()
    ctx.set_briefing("base")
    ctx.append_briefing("extra")
    assert "base" in ctx.briefing and "extra" in ctx.briefing


def test_build_summary_prompt_con_y_sin_previo():
    p1 = build_summary_prompt("", ["frase nueva"])
    assert "frase nueva" in p1 and "previo" not in p1.lower()
    p2 = build_summary_prompt("resumen viejo", ["otra"])
    assert "resumen viejo" in p2 and "otra" in p2


def test_load_briefing_source_archivo(tmp_path):
    f = tmp_path / "brief.md"
    f.write_text("Contexto del proyecto Acme")
    assert "Acme" in load_briefing_source(str(f))


def test_load_briefing_source_inexistente():
    assert load_briefing_source("/no/existe/xyz.txt") == ""


def test_load_briefing_source_directorio(tmp_path):
    (tmp_path / "a.txt").write_text("alpha")
    (tmp_path / "b.md").write_text("beta")
    (tmp_path / "c.bin").write_text("no-deberia-entrar")
    out = load_briefing_source(str(tmp_path))
    assert "alpha" in out and "beta" in out and "no-deberia-entrar" not in out
