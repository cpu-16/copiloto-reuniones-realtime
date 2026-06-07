from asistente.transcribe.correct import correct_terms
from asistente.transcribe.endpoint import segment_finals


# ---- corrección por similitud ----

def test_correct_sin_glosario_no_toca():
    assert correct_terms("hola kubernetis", []) == "hola kubernetis"


def test_correct_arregla_termino_casi_igual():
    out = correct_terms("usamos kubernetis en prod", ["Kubernetes"])
    assert "Kubernetes" in out


def test_correct_conserva_puntuacion():
    out = correct_terms("desplegamos en kubernetis.", ["Kubernetes"])
    assert out.endswith("Kubernetes.")


def test_correct_no_cambia_palabras_distintas():
    out = correct_terms("vamos a la casa", ["Kubernetes"])
    assert out == "vamos a la casa"


def test_correct_ignora_terminos_multipalabra():
    # un término con espacio no debe casarse contra una sola palabra
    out = correct_terms("hola rafael", ["Rafael Valdés"])
    assert out == "hola rafael"


def test_correct_no_daña_palabras_comunes_con_acronimos_cortos():
    # "plan" NO debe volverse "LAN", ni "rama" -> "RAM" (acrónimos < 5 letras = inertes)
    gloss = ["LAN", "RAM", "VPN", "DNS"]
    assert correct_terms("tenemos un plan claro", gloss) == "tenemos un plan claro"
    assert correct_terms("la rama principal", gloss) == "la rama principal"


def test_correct_si_aplica_a_nombres_de_producto_largos():
    # nombres de 5+ letras sí se corrigen
    assert "Proxmox" in correct_terms("instalamos proxmax", ["Proxmox"])
    assert "Cloudflare" in correct_terms("migramos a cloudflar", ["Cloudflare"])


# ---- endpointing / segmentación ----

def test_segment_una_frase_completa():
    finals, emitted, partial = segment_finals("Hola qué tal.", 0)
    assert finals == ["Hola qué tal."]
    assert partial == ""
    assert emitted == len("Hola qué tal.")


def test_segment_deja_parcial_sin_cerrar():
    finals, emitted, partial = segment_finals("Primera frase. Y esto sigue", 0)
    assert finals == ["Primera frase."]
    assert partial == "Y esto sigue"


def test_segment_incremental_no_repite_finales():
    full = "Uno. Dos. Tres en curso"
    finals1, emitted1, _ = segment_finals(full, 0)
    assert finals1 == ["Uno.", "Dos."]
    # en el siguiente paso el texto creció; partimos desde emitted1
    full2 = full + ". Cuatro"
    finals2, emitted2, partial2 = segment_finals(full2, emitted1)
    assert finals2 == ["Tres en curso."]
    assert partial2 == "Cuatro"


def test_segment_varios_signos():
    finals, _, partial = segment_finals("¿Vienes? ¡Sí!", 0)
    assert finals == ["¿Vienes?", "¡Sí!"]
    assert partial == ""
