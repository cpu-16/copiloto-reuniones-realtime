# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Qué es

Copiloto de reuniones **local**: captura el audio del sistema, lo transcribe en vivo en la GPU
y usa Claude (vía la suscripción, no API key) para sugerir respuestas y dar contexto, todo en una
ventanita flotante. Pensado para Fedora + Wayland + NVIDIA. Todo el procesamiento es local; solo el
**texto** de la transcripción va a Claude.

## Dos entornos virtuales (¡importante!)

Hay **dos motores ASR** y cada uno vive en su venv porque sus dependencias (torch) chocan:

- **`.venv`** — motor **whisper** (faster-whisper/RealtimeSTT). `pip install -e ".[dev]"`.
- **`.venv-parakeet`** — motor **parakeet** (NVIDIA NeMo, recomendado, más liviano). Se instala con `uv pip`
  (es un venv de uv, **no tiene `pip` propio**; usa `uv pip install --python .venv-parakeet ...`). El paquete
  `asistente` se instala ahí con `--no-deps` para no arrastrar las deps de whisper.

El motor se elige con `engine = "parakeet"|"whisper"` en `config.toml`. **Corre `run.py` con el venv que
corresponda al engine** o saldrá un error claro. Ambos venvs están gitignorados.

## Comandos

```bash
# Correr (Parakeet, recomendado; la 1ª carga del modelo tarda ~40s)
.venv-parakeet/bin/python run.py --native      # ventana nativa PySide6 (mejor en Wayland)
.venv-parakeet/bin/python run.py --no-window   # solo servidor; abre la URL en el navegador
# Whisper:
.venv/bin/python run.py --native

# Tests (corren en .venv; son unitarios de lógica pura, sin GPU/Claude)
.venv/bin/python -m pytest -q
.venv/bin/python -m pytest tests/test_copilot.py::test_parse_secciones -v

# De-risk / diagnóstico (scripts sueltos en scripts/)
.venv/bin/python scripts/derisk_audio.py --list          # encontrar el node-id del monitor del sink
.venv/bin/python scripts/diag_pipeline.py                # instrumenta captura→transcripción (con audio sonando)

# Atajo global mostrar/ocultar (GNOME; con el asistente corriendo)
bash scripts/set_hotkey.sh "<Super>a"
```

`config.toml` (copia de `config.example.toml`, gitignorado) controla todo: `engine`, `[audio] target`
(node-id del monitor del sink, p.ej. "122"), `[whisper]` (modelo, idioma, perillas de GPU), `[user]`
(names para detección + role para personalizar la IA), `[copilot]` (enabled, interval_s), `[server]` token.

## Arquitectura

Pipeline de 5 piezas, cada una con interfaz simple. `run.py` (en la raíz) es el ensamblador que las cablea:

```
PipeWire monitor → Transcriptor → Orquestador (FastAPI/WS) → UI flotante
  (pw-record)      (GPU, hilos)    │         ▲                (PySide6 nativa / web)
                                   ▼         │
                            Cerebro Claude (claude -p caliente)
```

- **`capture/pipewire.py`** — `PipeWireCapture.stream()` lanza `pw-record` y entrega chunks PCM s16 mono 16k.
- **`transcribe/`** — dos implementaciones con el **mismo interfaz** (`start(pcm_chunks, sr)`, `stop()`,
  callbacks `on_partial`/`on_final`): `whisper_stt.py` (RealtimeSTT) y `parakeet_stt.py` (NeMo + VAD por
  energía RMS). Emiten **parciales** (texto fluido mientras se habla) y **finales** (frase tras una pausa).
- **`server/app.py`** — `create_app(cfg, brain)`: sirve la UI, expone `/ws` (token-protegido), `/toggle`
  (atajo global) y `/health`. `app.state.broadcast(ev)` manda eventos a las UIs; `app.state.ctx` es el buffer
  de contexto compartido. Atiende `ask` (manual/botones) con el contexto reciente.
- **`brain/claude_client.py`** — `WarmClaude`: un proceso `claude -p` **persistente** alimentado por
  stream-json. Ver gotchas abajo.
- **`copilot.py`** — `build_copilot_prompt` + `parse_copilot`: el copiloto continuo (una llamada devuelve
  RESUMEN/IDEAS/BORRADOR/ALERTA, parseado por prefijos de línea).
- **`detect.py`** — heurística `is_question_for_me` (pregunta + dirigida a ti por nombre/segunda persona).
- **`events.py`** — contrato pydantic del WebSocket (la fuente de verdad de los tipos; las UIs lo consumen).
- **`ui/native.py`** — widget PySide6/QtWidgets (recomendado). **`ui/launcher.py`** (pywebview) y `ui/web/`
  (HTML/JS) son alternativas.

**Flujo de la IA** (todo en `run.py:main`): la transcripción se difunde como `transcript.partial/final`;
en cada texto se corre `is_question_for_me` (sobre **parciales y finales**) → si hay pregunta dirigida a ti,
se pide sugerencia a Claude (con cooldown). En paralelo, `copilot_loop` cada `interval_s` manda el contexto
a Claude y difunde un `Insight` (panel 🧠), guardando un **borrador** para responder al instante. Las llamadas
a `brain.ask` se serializan con un lock (un solo proceso/pipe).

## Gotchas y decisiones clave (lecciones aprendidas)

- **`claude -p` "descafeinado":** en frío tarda 5-9s. Se usa **caliente** (proceso persistente) y stripped:
  `--setting-sources "" --strict-mcp-config --allowed-tools "" --system-prompt ... --exclude-dynamic-system-prompt-sections`.
  Con eso el TTFT baja a ~2-3s tras un **prewarm** (1ª llamada dummy). **El parser DEBE ignorar `thinking_delta`**
  (Haiku piensa antes del texto) y recoger solo `text_delta`; el evento `result` cierra.
- **Parakeet OOM:** cargar el modelo `from_pretrained(map_location="cpu").half().to("cuda")` — si se carga
  directo en GPU el pico es ~5GB (fp32) y revienta la VRAM; en CPU→fp16→GPU el pico es ~1.3GB.
- **Idioma:** `[whisper] language = ""` ⇒ autodetección bilingüe (es/en). `"es"` lo fuerza (más rápido al arrancar).
- **Sugerencia proactiva en parciales:** con audio continuo de reunión casi nunca hay finales (necesitan
  silencio), así que la detección corre también sobre los parciales, no solo finales.
- **QtWebEngine segfaultea en este Wayland** → la ventana **pywebview** (sin flag) es inestable; usar `--native`
  (QtWidgets, estable) o `--no-window` (navegador). El widget nativo fuerza `QT_QPA_PLATFORM=xcb` (XWayland)
  para que frameless/always-on-top/arrastre funcionen.
- **Atajos globales en Wayland:** la app no puede capturarlos; se hace con un atajo de GNOME → `curl /toggle`
  → broadcast de un evento `toggle` → la ventana alterna visibilidad (el WS sigue vivo aunque esté oculta).
- **Cerrar mata el proceso:** el `closeEvent` llama `app.quit()` y `run.py` hace `os._exit(0)` (con cleanup
  con timeout), porque los hilos de NeMo/RealtimeSTT se cuelgan al apagar.
- **Puerto ocupado:** `run.py` revisa el puerto y avisa claro (en vez del traceback de uvicorn) si ya hay
  una instancia. Para matar una pegada: por el PID del puerto (`ss -ltnp | grep :8765`), no con `pkill -f run.py`
  (el wrapper del shell contiene "run.py" y se auto-mata).
- **Alucinaciones de Whisper/ASR** ("You", "¡Suscríbete!", "Thanks for watching" sobre silencio/música) se
  filtran en `transcribe/clean.py`.

## Estilo de pruebas

TDD/tests unitarios para lógica pura (events, config, detect, clean, copilot, claude framing, server WS).
Las piezas atadas a hardware/GPU/Claude se validan con scripts de de-risk "ejecuta y observa" (en `scripts/`),
no con tests automatizados.
