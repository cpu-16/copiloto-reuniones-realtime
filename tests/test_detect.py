from asistente.detect import is_question_for_me, looks_like_question

NAMES = ["Rafael", "Rafa"]


def test_pregunta_con_nombre():
    assert is_question_for_me("Rafa, ¿cómo va el proyecto?", NAMES)


def test_pregunta_segunda_persona():
    assert is_question_for_me("¿Tú qué opinas de esto?", NAMES)


def test_pregunta_pero_no_dirigida_a_mi():
    # Es pregunta, pero no me menciona ni usa segunda persona -> no dispara.
    assert not is_question_for_me("¿Cuándo sale el reporte trimestral?", NAMES)


def test_no_es_pregunta():
    assert not is_question_for_me("Rafa estuvo en la reunión de ayer.", NAMES)


def test_looks_like_question_sin_signos():
    # Whisper a veces no pone signos; cae en palabras interrogativas.
    assert looks_like_question("puedes explicar el plan")
