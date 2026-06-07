# Diseño — Mejoras: captura, historial, contexto y precisión ASR

Fecha: 2026-06-07
Estado: **implementado** (Fases A, B y C en código; la validación GPU de C la corre el usuario con `scripts/derisk_nemotron.py`)

## Estado de implementación

- **Fase A1** ✅ — `[parakeet] silence_rms`/`auto_calibrate`, autocalibración del piso de ruido (`calibrate_threshold`). Tests.
- **Fase A2** ✅ — panel acumula historial (`ui/history.py`), "pensando" al encabezado, auto-scroll, botón limpiar. Tests.
- **Fase B** ✅ — `context.py` (SessionContext 3 capas), resumen acumulativo en `copilot_loop`, eventos `briefing.set/state`, pestaña 📋 Contexto, ingestión `[context] briefing_file`. Tests.
- **Fase C** ✅ (código) — engine `nemotron` (`nemotron_stt.py`, streaming cache-aware), `endpoint.py`, `correct.py`, `[nemotron]`/`[asr]`, `scripts/derisk_nemotron.py`. **Pendiente: correr el de-risk en GPU con `.venv-nemotron`** (puerta C0) antes de hacerlo default.

## Motivación

Cuatro frentes detectados en uso real del copiloto:

1. **Umbral de captura rígido** — `silence_rms` está hardcoded; con audio bajo del sink no transcribe nada.
2. **El panel de respuestas a pedido pisa el historial** — al "actualizar" una pestaña se pierde la respuesta anterior.
3. **El copiloto pierde el enfoque en llamadas largas** — solo ve las últimas 12 frases; sin contexto durable salta de tema y se desorienta.
4. **Precisión del ASR en términos propios** — nombres y jerga técnica se transcriben mal.

Se agrupan en 3 fases por riesgo y sinergia. Orden recomendado: A → B → C.

## Verificación previa (hecha)

- NeMo instalado en `.venv-parakeet`: **2.7.3**.
- El módulo `nemo.collections.asr.parts.context_biasing` está presente y el **decoder greedy TDT** (el que usa parakeet por defecto) soporta `boosting_tree` + `boosting_tree_alpha` (`rnnt_decoding.py:351`). `BoostingTreeModelConfig` acepta `key_phrases_list: list[str]` — glosario como lista de Python, sin archivos. → El phrase boosting nativo de **parakeet** es viable (queda como plan de respaldo).

## Decisión de motor: migrar a Nemotron streaming

Se evaluó `nvidia/nemotron-3.5-asr-streaming-0.6b` (RNN-T FastConformer **cache-aware**) y se decide **migrar a él** como motor principal, conservando parakeet como respaldo conmutable. Motivos: streaming nativo de baja latencia (vs. el hack actual de re-transcribir el buffer con VAD-RMS) y mejor WER en español (**4.11%** FLEURS, contexto 1.12s). Esto convierte la Fase C en una **migración de motor** (ver abajo).

Hechos verificados de la fuente:
- Requiere **NeMo 26.06 / git main** (`pip install git+https://github.com/NVIDIA/NeMo.git@main#egg=nemo_toolkit[asr]`). El `.venv-parakeet` (2.7.3) **no sirve** → venv nuevo.
- Carga igual: `ASRModel.from_pretrained("nvidia/nemotron-3.5-asr-streaming-0.6b")`. ~2.4GB. Mono 16k (lo que pw-record ya da; sin resample).
- Streaming: `model.encoder.get_initial_cache_state(batch_size=1)` → `model.conformer_stream_step(processed_signal, processed_signal_length, cache_last_channel, cache_last_time, cache_last_channel_len, keep_all_outputs, previous_hypotheses, previous_pred_out, drop_extra_pre_encoded, return_transcription=True)` por chunk, mantiene cachés + `previous_hypotheses` + `pred_out_stream` entre pasos.
- `model.encoder.set_default_att_context_size([56,13])` (1120ms, mejor precisión; bajar a `[56,6]`/560ms o `[56,3]`/320ms por latencia). `target_lang="es"` o `"auto"`, `strip_lang_tags=true`.
- Context biasing para nemotron: **incógnita** en NeMo 26.06 → se verifica en la puerta C0.

---

## Fase A — Umbral de captura configurable + historial del panel

Bajo riesgo, alivio inmediato. No toca el cerebro ni el contexto.

### A1. Umbral de captura (`silence_rms`)

**Problema:** `ParakeetTranscriber.__init__` fija `silence_rms=350.0` (`parakeet_stt.py:23`) y `run.py:149` no lo pasa desde config. Si el RMS del sink nunca cruza 350, `_had_speech` jamás se activa y el worker no transcribe (`parakeet_stt.py:99`).

**Diseño:**
- Nuevo bloque en `config.toml`:
  ```toml
  [parakeet]
  silence_rms = 0          # 0 = autocalibrar; >0 = umbral fijo manual
  auto_calibrate = true    # mide el piso de ruido al arrancar
  ```
- `config.py`: añadir dataclass `ParakeetCfg(silence_rms: float = 0.0, auto_calibrate: bool = True)` y exponerla en `Config`. Mantener defaults retro-compatibles.
- `run.py`: pasar `silence_rms` y `auto_calibrate` al construir `ParakeetTranscriber`.
- **Autocalibración** en `ParakeetTranscriber`: durante los primeros ~1.5 s de audio (en `feed`), acumular RMS por chunk sin marcar voz; al cerrar la ventana de calibración, fijar `silence_rms = max(piso_ruido * FACTOR, MIN_RMS)` con `FACTOR≈2.5`, `MIN_RMS≈120`. Si el usuario fijó un valor manual (`silence_rms>0` y `auto_calibrate=false`), se respeta tal cual.
- **Observabilidad:** imprimir en consola el RMS de cada ventana de calibración y el umbral final elegido, para que el usuario pueda afinar a mano si quiere.

**Componentes/efectos:** `parakeet_stt.py` (lógica de calibración), `config.py` (nuevo bloque), `run.py` (cableado), `config.example.toml` (documentar). Whisper no se toca.

> **Nota tras decidir migrar a Nemotron:** el umbral RMS es propio de parakeet. El streaming cache-aware de nemotron **no gatea por energía** (el audio fluye continuo), así que el problema "tengo que ajustar el micro para que capture" **desaparece** cuando nemotron sea el motor. A1 se mantiene solo como *stopgap* mientras parakeet siga activo/como respaldo; es de bajo esfuerzo. Si la migración avanza rápido, A1 puede recortarse.

**Tests:** unitarios de `config.py` (parsea el nuevo bloque, defaults). La calibración se valida con script de de-risk "ejecuta y observa" (depende de audio real).

### A2. Historial del panel de respuestas

**Problema:** el handler del evento `answer` hace `edit.setPlainText(...)` (`native.py:418`), que reemplaza. `_ask_tab` también pone `setPlainText("⏳ pensando…")` (`native.py:352`). Al pulsar "🔄 actualizar" se re-consulta y se pierde lo anterior.

**Aclaración de costo:** mostrar/guardar historial es 100% local (render en `QTextEdit`); **no consume tokens**. El costo es la llamada a Claude, que ocurre igual con o sin historial.

**Diseño (solo `native.py`):**
- En lugar de pisar el texto, **`append()`** cada respuesta nueva con un separador y hora local, p. ej.:
  ```
  ── 09:57 ─────────────
  <respuesta>
  ```
- El estado "⏳ pensando…" deja de escribirse en el cuerpo del `QTextEdit`; va al **encabezado de la pestaña** (`panel_hdr`) o a `status`. Al llegar la respuesta, se **añade** debajo de las anteriores.
- Auto-scroll al final tras cada `append` (igual que la transcripción, `native.py:414`).
- Añadir botón **"limpiar pestaña"** en `actrow` para vaciar la pestaña activa a voluntad.
- `_loaded`/`_pending` siguen igual; "actualizar" sigue re-consultando, pero ahora **acumula** en vez de borrar.

**Tests:** la UI no tiene tests automatizados (atada a Qt); se valida ejecutando. Sí se puede testear cualquier helper puro que se extraiga (formato del separador/hora).

---

## Fase B — Contexto en 3 capas (que no pierda el enfoque)

El cambio de mayor impacto. Reescribe el contexto de 1 capa (`deque(maxlen=12)`) a 3 capas con presupuesto de tokens, y **unifica** la construcción de prompts.

### Estado actual

`run.py:62` crea `ctx = deque(maxlen=12)` y lo comparte por `app.state.ctx`. Tres consumidores arman el prompt por separado:
- `copilot_loop` → `build_copilot_prompt` (`copilot.py:9`)
- `suggest_for` (`run.py:74`)
- `_ask_prompt` (`app.py:22`)

### Diseño

**Nuevo módulo `src/asistente/context.py`** con una clase `SessionContext`:

- **Capa 1 — Briefing (durable):** `briefing: str`. Texto corto editable (proyecto, participantes, objetivos, términos). Se carga de: (a) `config.toml [context] briefing = "..."` o `briefing_file = "ruta"`, y/o (b) edición en vivo desde la UI. Si se da `briefing_file` o `briefing_path`, se lee y se **resume una sola vez al inicio** con una llamada a Claude, y el resumen pasa a ser el briefing. Sin RAG/vector DB (YAGNI para un solo proyecto).
- **Capa 2 — Resumen acumulativo:** `running_summary: str`. Cada N finales (reusando el ciclo del copiloto), Claude actualiza un resumen del hilo y **reemplaza** el anterior (no crece). Mantiene el foco entre cambios de tema.
- **Capa 3 — Ventana rodante:** `window: deque(maxlen=12)`. Las últimas frases para inmediatez (lo actual).

**Método central** `compose(max_chars: int) -> str` que ensambla las 3 capas con prioridad (briefing > resumen > ventana) y recorta al presupuesto para no inflar tokens:
```
[BRIEFING]
<briefing>

[RESUMEN HASTA AHORA]
<running_summary>

[ÚLTIMO]
<window unida>
```

**Unificación de prompts:** `build_copilot_prompt`, `suggest_for` y `_ask_prompt` pasan a recibir el `SessionContext` (o el string de `compose()`) en vez del `"\n".join(ctx)` crudo. Una sola fuente de verdad del contexto.

**Resumen acumulativo (mecánica):** en `copilot_loop` (`run.py:89`), tras difundir el `Insight`, si hubo suficientes finales nuevos, pedir a Claude un resumen incremental: prompt = resumen anterior + frases nuevas → nuevo resumen. Guardar en `SessionContext.running_summary`. Se reusa el mismo lock/pipe (un solo proceso Claude).

**UI del briefing:** 
- Campo/área para ver y editar el briefing (puede ir en una pestaña nueva del panel, p. ej. "📋 Contexto", o un pequeño editor colapsable).
- Nuevo evento cliente→servidor `briefing.set` (en `events.py`) que actualiza `SessionContext.briefing`.
- Acción "cargar archivo/ruta": el usuario indica una ruta; el server la lee, la resume una vez y la mete al briefing. Lectura **acotada** (límite de tamaño; si es directorio, concatenar archivos de texto relevantes hasta un tope) para no reventar el contexto.

**Eventos (`events.py`):** añadir `BriefingSet(text)` (cliente→servidor) y opcionalmente `BriefingState(text)` (servidor→UI) para sincronizar el contenido entre UIs. Mantener el contrato pydantic como fuente de verdad.

**Presupuesto de tokens:** `compose()` recorta por `max_chars`. El briefing y el resumen son cortos por diseño; la ventana es la que más varía. Esto evita que el contexto durable infle cada llamada.

**Componentes/efectos:** `context.py` (nuevo), `run.py` (usar `SessionContext`, resumen incremental, ingestión inicial), `copilot.py` (firma de `build_copilot_prompt`), `app.py` (`_ask_prompt` + manejar `BriefingSet`), `events.py` (nuevos eventos), `native.py` (UI del briefing), `config.py` + `config.example.toml` (bloque `[context]`).

**Tests:** unitarios de `SessionContext` (compose respeta prioridad y presupuesto; reemplazo del resumen; ventana rodante), de `events.py` (nuevos eventos parsean), de `app.py` WS (maneja `BriefingSet`). El resumen incremental real (calidad) se valida ejecutando.

---

## Fase C — Migración a Nemotron streaming cache-aware

Reemplaza el motor por `nvidia/nemotron-3.5-asr-streaming-0.6b`, conservando parakeet como respaldo conmutable por `config.toml`. Es lo más ambicioso y de mayor riesgo (NeMo nuevo + refactor del transcriptor), por eso va de último y arranca con una puerta de verificación bloqueante.

### C0 — Setup del venv + puerta de verificación (PRIMERO, bloqueante)

- Crear venv nuevo `.venv-nemotron` (uv) con **NeMo git main pinneado a un commit** (no flotante) e instalar `asistente --no-deps`. **No tocar `.venv-parakeet`** (sigue siendo el respaldo funcional).
- Script `scripts/derisk_nemotron.py`: carga el modelo (CPU→fp16→cuda, OOM-safe), corre streaming cache-aware sobre un wav de prueba en español **con tus términos**, imprime parciales + latencia, y lo compara con parakeet. Verifica además si el RNN-T acepta `boosting_tree` (context biasing) en esta versión de NeMo.
- **Gate:** no se pasa a C1 hasta que esto cargue, transcriba bien y la latencia convenza. Si nemotron no carga o no convence → se **aborta la migración** y se cae al plan de respaldo (parakeet + phrase boosting, ya verificado viable). Esto protege contra el riesgo de NeMo git-main.

### C1 — Transcriptor streaming `nemotron_stt.py`

- **Misma interfaz** que los otros transcriptores (`start(pcm_chunks, sr)`, `stop()`, callbacks `on_partial`/`on_final`), para que `run.py` lo cablee sin cambios estructurales.
- Loop de streaming: PCM de pw-record → preprocesador/buffer cache-aware (mel) → `conformer_stream_step(...)` por chunk, mantieniendo `cache_last_channel/last_time/last_channel_len`, `previous_hypotheses` y `pred_out_stream` entre pasos. El texto incremental que devuelve se emite como **parcial**.
- `set_default_att_context_size(...)` y `target_lang` configurables (ver `[nemotron]`). Carga OOM-safe como parakeet.
- Adiós al hack actual: ya **no** se re-transcribe el buffer entero ni se gatea por VAD-RMS.

### C2 — Endpointing (parcial → final)

- Con streaming continuo los parciales salen solos. Los **finales** (lo que entra al contexto de Fase B y dispara `is_question_for_me`) se cierran por: puntuación (el modelo puntúa nativo) y/o pausa (sin tokens nuevos por X ms). Reutilizar/adaptar `clean.py` para filtrar alucinaciones.

### C3 — Glosario (según resultado de C0)

- Si el RNN-T de nemotron acepta el boosting tree en NeMo nuevo → glosario nativo (`[asr] glossary`), igual que el respaldo de parakeet.
- Si no → **corrección local por similitud** sobre los finales: función pura sin LLM, tokens con baja distancia de edición a un término del glosario se sustituyen. Gratis y rápido. El glosario comparte la idea de "vocabulario del proyecto" con el briefing (Fase B).

### C4 — Conmutación de motor

- Añadir `engine = "nemotron"` y bloque `[nemotron]` (`model`, `att_context_size`, `target_lang`) en config. `run.py` cablea el nuevo transcriptor por engine. Tras validar en uso real, nemotron pasa a **recomendado/default**; parakeet y whisper quedan como alternativas.
- Actualizar `CLAUDE.md` (tres venvs ahora) y `config.example.toml`.

**Componentes/efectos:** `nemotron_stt.py` (nuevo), `scripts/derisk_nemotron.py` (nuevo), `run.py` (engine `nemotron`), `config.py` + `config.example.toml` (`[nemotron]`, `[asr]`), `clean.py` (reuso de filtros), `CLAUDE.md` (venv nuevo). `parakeet_stt.py`/`whisper_stt.py` no se rompen (quedan como respaldo).

**Tests:** unitarios de la corrección por similitud (función pura) y del endpointing por puntuación/pausa si se extrae a función pura. La carga, el streaming y la latencia se validan con `scripts/derisk_nemotron.py` (atado a GPU/modelo).

---

## Lo que NO se hace (YAGNI)

- RAG / base vectorial para el contexto (un resumen alcanza para un proyecto).
- Fine-tuning del ASR.
- Borrar parakeet/whisper — quedan como motores de respaldo conmutables, no se eliminan.
- Persistencia en base de datos del historial del panel (acumular en memoria de la sesión basta).

## Orden de implementación

1. **Fase A** (A1 + A2) — independientes y de bajo riesgo. *(A1 es stopgap de parakeet; si la migración a nemotron avanza, A1 puede recortarse — ver nota en A1.)*
2. **Fase B** — el grueso del valor; introduce `context.py` y unifica prompts. Agnóstica al motor.
3. **Fase C** — migración a nemotron. **C0 (verificación) es bloqueante**: si falla, se cae al respaldo parakeet+boosting sin perder el resto del plan.

## Riesgos principales

- **NeMo git-main inestable:** pinnear commit; el venv nuevo aísla el riesgo del `.venv-parakeet` que ya funciona.
- **API `conformer_stream_step` / alineación de chunks vs `att_context_size`:** es el corazón del refactor; el de-risk C0 debe clavarlo antes de integrar.
- **Context biasing incierto en nemotron:** mitigado con el fallback de corrección local (C3).
- **VRAM/latencia en tu GPU:** se mide en C0 antes de comprometer.
