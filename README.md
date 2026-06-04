# Asistente de Reuniones en Tiempo Real

Copiloto local: transcribe reuniones en vivo (en la GPU) y sugiere respuestas
(Claude vía tu suscripción), en una ventanita flotante. Detecta cuándo te preguntan
a ti y te arma la respuesta con el contexto de la reunión.

## Requisitos
- Fedora con PipeWire, GPU NVIDIA, `claude` CLI autenticado.
- Python 3.12.

## Dos motores de transcripción

| Motor | VRAM | Velocidad | Idiomas | Venv |
|-------|------|-----------|---------|------|
| **parakeet** (recomendado) | ~1.3 GB | rapidísimo (transductor) | es/en + 23 (autodetecta) | `.venv-parakeet` |
| **whisper** | ~2.9 GB | rápido | es/en (autodetecta) | `.venv` |

Eliges con `engine = "parakeet"` o `"whisper"` en `config.toml`.

## Instalación

**Motor Whisper (`.venv`):**
```bash
python3.12 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
```

**Motor Parakeet (`.venv-parakeet`, NeMo):**
```bash
uv venv .venv-parakeet --python 3.12
uv pip install --python .venv-parakeet "nemo_toolkit[asr]" fastapi "uvicorn[standard]" \
    websockets "pydantic>=2.7" pywebview PySide6 qtpy setuptools
uv pip install --python .venv-parakeet -e . --no-deps
```

Luego:
```bash
cp config.example.toml config.toml   # y edítalo
```

## Configurar el audio
```bash
python scripts/derisk_audio.py --list      # encuentra el monitor del sink (node-id)
```
Pon ese target en `config.toml` -> `[audio] target`.

## Correr

Usa el venv que corresponda al `engine` de tu `config.toml`:

```bash
# Parakeet (recomendado)
.venv-parakeet/bin/python run.py --native

# Whisper
.venv/bin/python run.py --native
```

Modos de ventana:
- `--native`  : widget nativo PySide6 (recomendado en Wayland).
- `--no-window`: solo servidor; abres la UI en el navegador (la URL que imprime).
- (sin flag)  : ventana pywebview (QtWebEngine, inestable en algunos Wayland).

En la ventana: arrástrala donde quieras; botón **tema** (oscuro/claro/vidrio),
**–** minimizar, **⤢** expandir, **✕** cerrar (mata el proceso). Transcripción en
vivo (cursiva = parcial, sólido = confirmado); cuando te preguntan, la sugerencia
aparece sola; o escribe en la caja para preguntarle a Claude con contexto.

## Bajar el consumo de GPU
En `config.toml` -> `[whisper]` (aplica al motor whisper): `realtime_model="base"/"tiny"`,
sube `realtime_pause`, o `enable_realtime=false`. Con **parakeet** ya es liviano de fábrica.

## Estado
MVP funcional: transcripción bilingüe en vivo, sugerencia proactiva con contexto,
ventana flotante con temas. Dos motores (Parakeet/Whisper). Próximo: UI en segundo
dispositivo para ocultarla al compartir pantalla.
