from asistente.transcribe.clean import is_hallucination, strip_lang_tags


def test_strip_lang_tags_quita_etiquetas():
    assert strip_lang_tags("<es-US> Hola mundo") == "Hola mundo"
    assert strip_lang_tags("<en-US>Hello there") == "Hello there"
    assert strip_lang_tags("uno <es-US> dos <en-US> tres") == "uno dos tres"


def test_strip_lang_tags_sin_etiquetas_no_toca():
    assert strip_lang_tags("texto normal") == "texto normal"
    # no debe comerse comparaciones tipo "a < b > c" (no son etiquetas de idioma)
    assert strip_lang_tags("a < b > c") == "a < b > c"


def test_filtra_basura_conocida():
    assert is_hallucination("You")
    assert is_hallucination("¡Suscríbete!")
    assert is_hallucination("Thanks for watching!")
    assert is_hallucination("   ")


def test_no_filtra_habla_legitima():
    assert not is_hallucination("Sí, estoy de acuerdo.")
    assert not is_hallucination("No, prefiero esperar.")
    assert not is_hallucination("¿Cómo va el proyecto?")
    assert not is_hallucination("You should review the report")  # frase real con 'you'
