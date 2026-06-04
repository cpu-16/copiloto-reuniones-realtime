from asistente.transcribe.clean import is_hallucination


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
