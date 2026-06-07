"""Tests del helper puro de autocalibración del umbral (sin GPU/NeMo: el import de
NeMo en ParakeetTranscriber es perezoso, así que importar el módulo es seguro)."""
from asistente.transcribe.parakeet_stt import calibrate_threshold


def test_calibrate_vacio_devuelve_minimo():
    assert calibrate_threshold([], min_rms=120.0) == 120.0


def test_calibrate_escala_el_piso_de_ruido():
    # piso de ruido ~100 → percentil20≈100, *2.5 = 250 (> min)
    ruido = [100.0] * 50
    assert calibrate_threshold(ruido, factor=2.5, min_rms=120.0) == 250.0


def test_calibrate_respeta_minimo_si_silencio_total():
    # casi silencio: percentil20≈10, *2.5=25 < min → gana el mínimo
    assert calibrate_threshold([10.0] * 50, factor=2.5, min_rms=120.0) == 120.0


def test_calibrate_robusto_ante_algo_de_voz():
    # mayormente ruido bajo con picos de voz: el percentil20 ignora los picos
    valores = [80.0] * 40 + [3000.0] * 10   # 20% son voz alta
    umbral = calibrate_threshold(valores, factor=2.5, min_rms=120.0)
    assert 150.0 <= umbral <= 260.0   # ~80*2.5=200, no arrastrado por los 3000
