# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Qué es

Copiloto de reuniones **local**: captura el audio del sistema, lo transcribe en vivo en la GPU
y usa un LLM (Claude vía suscripción **o** un modelo local con Ollama) para sugerir respuestas y dar
contexto, todo en una ventanita flotante. Pensado para Fedora + Wayland + NVIDIA. Todo el procesamiento
es local; con Claude solo el **texto** de la transcripción sale del equipo; con Ollama nada sale.

## Tres entornos virtuales (¡importante!)

Hay **tres motores ASR** y cada uno vive en su venv porque sus dependencias (torch/NeMo) chocan:

- **`.venv`** — motor **whisper** (faster-whisper/RealtimeSTT). `pip install -e ".[dev]"`.
- **`.venv-parakeet`** — motor **parakeet** (NVIDIA NeMo 2.7.x, liviano, *respaldo*). Se instala con `uv pip`
  (es un venv de uv, **no tiene `pip` propio**; usa `uv pip install --python .venv-parakeet ...`). El paquete
  `asistente` se instala ahí con `--no-deps` para no arrastrar las deps de whisper.
- **`.venv-nemotron`** — motor **nemotron** (NVIDIA Nemotron 3.5 ASR streaming 0.6B, cache-aware, *recomendado*).
  Requiere **NeMo 26.06 / git main** (`uv pip install --python .venv-nemotron "nemo_toolkit[asr] @ git+https://github.com/NVIDIA/NeMo.git@<commit>"`)
  + `asistente --no-deps`. Streaming nativo de baja latencia y mejor WER en español. **Antes de confiar en él,
  corre la puerta de verificación** `scripts/derisk_nemotron.py` (carga, latencia, glosario).

El motor se elige con `engine = "nemotron"|"parakeet"|"whisper"` en `config.toml`. **Corre `run.py` con el venv que
corresponda al engine** o saldrá un error claro. Los tres venvs están gitignorados.

## Comandos

```bash
# Correr (Nemotron, recomendado; la 1ª vez descarga el modelo ~2.4GB)
.venv-nemotron/bin/python run.py --native              # ventana nativa PySide6 (mejor en Wayland)
.venv-nemotron/bin/python run.py --native --engine parakeet   # --engine pisa el config
.venv/bin/python run.py --native --engine whisper             # whisper (corre en CPU con [whisper] device="cpu")
.venv-nemotron/bin/python run.py --no-window           # solo servidor; abre la URL (útil en 2da pantalla)

# Tests (corren en .venv; son unitarios de lógica pura, sin GPU/Claude)
.venv/bin/python -m pytest -q

# De-risk / diagnóstico (scripts sueltos en scripts/)
.venv/bin/python scripts/derisk_audio.py --list          # node-id del monitor del sink
.venv-nemotron/bin/python scripts/derisk_nemotron.py --wav muestra_es.wav   # puerta C0 de Nemotron
.venv/bin/python scripts/derisk_ollama.py --model gemma4:e2b                # latencia de un LLM local

# Atajos globales (GNOME; con el asistente corriendo)
bash scripts/set_hotkey.sh "<Super>a"          # mostrar/ocultar (/toggle)
bash scripts/set_hotkey.sh "<Super>g" ghost    # modo fantasma / click-through (/ghost)
```

`config.toml` (copia de `config.example.toml`, gitignorado) controla todo: `engine`
(`nemotron|parakeet|whisper`), `[brain] backend` (`claude|ollama`) + `[ollama]` (model/host),
`[nemotron]` (att_context_size, target_lang) y `[asr]` (glossary), `[context]` (briefing,
briefing_file, window, summary_every), `[audio] target` (node-id del monitor, p.ej. "122"),
`[whisper]` (modelo, idioma, `device` cuda/cpu), `[parakeet]` (silence_rms/autocalibración),
`[user]` (names + role), `[copilot]` (enabled, interval_s), `[server]` token.

## Arquitectura

Pipeline de 5 piezas, cada una con interfaz simple. `run.py` (en la raíz) es el ensamblador que las cablea:

```
PipeWire monitor → Transcriptor → Orquestador (FastAPI/WS) → UI flotante
  (pw-record)      (GPU, hilos)    │         ▲                (PySide6 nativa / web)
                                   ▼         │
                         Cerebro (Claude -p caliente / Ollama local)
```

- **`capture/pipewire.py`** — `PipeWireCapture.stream()` lanza `pw-record` y entrega chunks PCM s16 mono 16k.
- **`transcribe/`** — **tres** implementaciones con el **mismo interfaz** (`start(pcm_chunks, sr)`, `stop()`,
  callbacks `on_partial`/`on_final`): `nemotron_stt.py` (NeMo cache-aware streaming, recomendado),
  `parakeet_stt.py` (NeMo + VAD RMS, con autocalibración del umbral) y `whisper_stt.py` (RealtimeSTT, único
  que corre en CPU). Helpers puros: `clean.py` (filtra alucinaciones + quita etiquetas `<es-US>`),
  `correct.py` (corrige el glosario por similitud), `endpoint.py` (segmenta el stream acumulado en finales).
- **`context.py`** — `SessionContext`: contexto en **3 capas** (briefing durable + resumen acumulativo +
  ventana rodante) con `compose(max_chars)`. Fuente única que alimentan copiloto, sugerencia y "preguntar".
- **`server/app.py`** — `create_app(cfg, brain)`: sirve la UI, expone `/ws` (token), `/toggle` (mostrar/ocultar),
  `/ghost` (modo fantasma) y `/health`. `app.state.broadcast(ev)` manda eventos; `app.state.ctx` es el
  `SessionContext` compartido. Atiende `ask` y `briefing.set`.
- **`brain/`** — cerebro intercambiable por `[brain] backend`: `claude_client.py` (`WarmClaude`, proceso
  `claude -p` persistente, stream-json) u `ollama_client.py` (`OllamaBrain`, LLM local vía HTTP). Mismo
  interfaz `ask/prewarm/stop`.
- **`copilot.py`** — `build_copilot_prompt` + `parse_copilot` (RESUMEN/IDEAS/BORRADOR/ALERTA por prefijos).
- **`detect.py`** — heurística `is_question_for_me` (pregunta + dirigida a ti por nombre/segunda persona).
- **`events.py`** — contrato pydantic del WebSocket (la fuente de verdad de los tipos; las UIs lo consumen).
- **`ui/native.py`** — widget PySide6/QtWidgets (recomendado), con temas, panel de respuestas (`ui/history.py`),
  modo fantasma. **`ui/launcher.py`** (pywebview) y `ui/web/` (HTML/JS) son alternativas.

**Flujo de la IA** (todo en `run.py:main`): la transcripción se difunde como `transcript.partial/final` y entra
al `SessionContext`; en cada texto se corre `is_question_for_me` (sobre **parciales y finales**) → si hay
pregunta dirigida a ti, se pide sugerencia al cerebro (con cooldown + guard "en vuelo"). En paralelo,
`copilot_loop` cada `interval_s` manda `ctx.compose()` al cerebro, difunde un `Insight` (panel 🧠), guarda un
**borrador** para responder al instante, y cada N finales actualiza el resumen acumulativo. Las llamadas a
`brain.ask` se serializan con un lock.

## Gotchas y decisiones clave (lecciones aprendidas)

- **`claude -p` "descafeinado":** en frío tarda 5-9s. Se usa **caliente** (proceso persistente) y stripped:
  `--setting-sources "" --strict-mcp-config --allowed-tools "" --system-prompt ... --exclude-dynamic-system-prompt-sections`.
  Con eso el TTFT baja a ~2-3s tras un **prewarm** (1ª llamada dummy). **El parser DEBE ignorar `thinking_delta`**
  (Haiku piensa antes del texto) y recoger solo `text_delta`; el evento `result` cierra.
- **Parakeet OOM:** cargar el modelo `from_pretrained(map_location="cpu").half().to("cuda")` — si se carga
  directo en GPU el pico es ~5GB (fp32) y revienta la VRAM; en CPU→fp16→GPU el pico es ~1.3GB.
- **Nemotron — prompt de idioma:** es `EncDecRNNTBPEModelWithPrompt`. Sin `model.set_inference_prompt("es"|"auto")`
  decodifica **vacío** (concatena un one-hot de idioma al encoder en cada chunk). El modo `"auto"` emite
  etiquetas `<es-US>`/`<en-US>` → se quitan con `clean.strip_lang_tags`.
- **Nemotron — fp32 + sin CUDA graphs:** en fp16 el decoder RNN-T con CUDA graphs mezcla dtypes ("mat1 and
  mat2 must have the same dtype"). Se corre en **fp32** (~2.7GB) y se desactiva `greedy.use_cuda_graph_decoder`
  (los chunks de streaming cambian de tamaño y los graphs asumen forma fija).
- **Nemotron — no comerse palabras:** usar `CacheAwareStreamingAudioBuffer` (preprocesa el audio UNA vez) en
  vez de re-preprocesar ventanas, y consumir SOLO chunks completos (`available >= chunk_size`; el `__iter__`
  del buffer no valida tamaño y avanzaría `buffer_idx` de más, saltando audio).
- **Nemotron — sesiones largas:** el RNN-T acumula la hipótesis sin límite; se fuerza un final por pausa o por
  largo (`max_partial_chars`) y se **reinicia la hipótesis** del decoder cuando no queda pendiente (el cache
  acústico del encoder se mantiene), o la sesión se ralentiza hasta congelarse.
- **Idioma:** `[whisper] language = ""` ⇒ autodetección bilingüe (es/en). `"es"` lo fuerza (más rápido al arrancar).
- **Sugerencia proactiva en parciales:** con audio continuo de reunión casi nunca hay finales (necesitan
  silencio), así que la detección corre también sobre los parciales, no solo finales.
- **QtWebEngine segfaultea en este Wayland** → la ventana **pywebview** (sin flag) es inestable; usar `--native`
  (QtWidgets, estable) o `--no-window` (navegador). El widget nativo fuerza `QT_QPA_PLATFORM=xcb` (XWayland)
  para que frameless/always-on-top/arrastre funcionen.
- **Atajos globales en Wayland:** la app no puede capturarlos; se hace con un atajo de GNOME → `curl /toggle`
  o `/ghost` → broadcast de un evento → la ventana alterna visibilidad o modo fantasma (el WS sigue vivo aunque
  esté oculta o atravesable).
- **Stealth real en Wayland = imposible desde la app:** el compositor ya pintó la ventana en el frame que se
  comparte y ningún protocolo (`xdg-desktop-portal`, `wlr-screencopy`) ofrece exclusión por ventana. La
  discreción es: compartir una ventana (no la pantalla), 2da pantalla, o **modo fantasma** (click-through vía
  `Qt.WindowTransparentForInput`). El stealth de verdad será del port a Windows (`WDA_EXCLUDEFROMCAPTURE`).
- **Cerrar mata el proceso:** el `closeEvent` llama `app.quit()` y `run.py` hace `os._exit(0)` (con cleanup
  con timeout), porque los hilos de NeMo/RealtimeSTT se cuelgan al apagar.
- **Puerto ocupado:** `run.py` revisa el puerto y avisa claro (en vez del traceback de uvicorn) si ya hay
  una instancia. Para matar una pegada: por el PID del puerto (`ss -ltnp | grep :8765`), no con `pkill -f run.py`
  (el wrapper del shell contiene "run.py" y se auto-mata).
- **Alucinaciones de Whisper/ASR** ("You", "¡Suscríbete!", "Thanks for watching" sobre silencio/música) se
  filtran en `transcribe/clean.py`.

## Estilo de pruebas

TDD/tests unitarios para lógica pura (events, config, detect, clean, copilot, context, history, ollama,
corrección+endpointing del ASR, claude framing, server WS). Las piezas atadas a hardware/GPU/LLM se validan
con scripts de de-risk "ejecuta y observa" (en `scripts/`), no con tests automatizados.
