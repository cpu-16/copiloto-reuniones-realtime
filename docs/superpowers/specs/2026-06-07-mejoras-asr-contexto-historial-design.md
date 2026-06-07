# Diseño — Mejoras: captura, historial, contexto y precisión ASR

Fecha: 2026-06-07
Estado: propuesto (pendiente de revisión del usuario)

## Motivación

Cuatro frentes detectados en uso real del copiloto:

1. **Umbral de captura rígido** — `silence_rms` está hardcoded; con audio bajo del sink no transcribe nada.
2. **El panel de respuestas a pedido pisa el historial** — al "actualizar" una pestaña se pierde la respuesta anterior.
3. **El copiloto pierde el enfoque en llamadas largas** — solo ve las últimas 12 frases; sin contexto durable salta de tema y se desorienta.
4. **Precisión del ASR en términos propios** — nombres y jerga técnica se transcriben mal.

Se agrupan en 3 fases por riesgo y sinergia. Orden recomendado: A → B → C.

## Verificación previa (hecha)

- NeMo instalado en `.venv-parakeet`: **2.7.3**.
- El módulo `nemo.collections.asr.parts.context_biasing` está presente y el **decoder greedy TDT** (el que usa parakeet por defecto) soporta `boosting_tree` + `boosting_tree_alpha` (`rnnt_decoding.py:351`).
- `BoostingTreeModelConfig` acepta `key_phrases_list: list[str]` — el glosario se pasa como lista de Python, sin archivos. Se activa con `model.change_decoding_strategy(...)`.

→ El phrase boosting nativo es viable; deja de ser incógnita.

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

## Fase C — Precisión del ASR (phrase boosting + recorte de silencio)

Última por depender de NeMo, ya verificado viable.

### C1. Recorte de silencio antes de transcribir

**Problema:** `_transcribe` concatena todo `self._buf`, incluido el silencio previo/posterior al habla (`parakeet_stt.py:53`). Meterle silencio al modelo degrada la salida.

**Diseño:** antes de pasar el audio al modelo, recortar tramos de RMS por debajo del umbral al inicio y al final (no en el medio, para no cortar pausas naturales). Operación numpy barata. Se apoya en el mismo umbral de la Fase A.

### C2. Glosario + phrase boosting nativo (NeMo)

**Diseño:**
- Nuevo en `config.toml`:
  ```toml
  [asr]
  glossary = ["Kubernetes", "Rafael Valdés", "<términos del proyecto>"]
  boosting_alpha = 4.0     # peso del sesgo; 0 = desactivado
  ```
  El glosario puede **derivarse/compartirse** con los términos del briefing (Fase B): misma idea de "vocabulario del proyecto".
- En `ParakeetTranscriber`, tras cargar el modelo: si hay glosario, construir `BoostingTreeModelConfig(key_phrases_list=glossary, ...)` y aplicarlo vía `model.change_decoding_strategy(...)` sobre el **decoder greedy** (camino actual). Parámetros (`context_score`, `boosting_tree_alpha`) configurables con defaults sensatos.
- **De-risk primero:** script `scripts/derisk_boosting.py` que carga el modelo, aplica el boosting con un glosario de prueba y compara transcripción con/sin boosting sobre un wav. Confirma la API real de 2.7.3 antes de integrarlo en el pipeline.

### C3. (Opcional/complemento) Corrección local por similitud

Si el boosting no alcanza para algún término, corrección post-ASR **sin LLM** sobre los finales: tokens con baja distancia de edición a un término del glosario se sustituyen. Gratis y rápido. Se implementa solo si C2 se queda corto.

**Componentes/efectos:** `parakeet_stt.py` (recorte + boosting + corrección opcional), `config.py` + `config.example.toml` (bloque `[asr]`), `scripts/derisk_boosting.py` (nuevo). Whisper no se toca.

**Tests:** unitarios de la corrección por similitud (función pura: entrada ruidosa + glosario → corregido). El boosting nativo se valida con el script de de-risk (atado a GPU/modelo).

---

## Lo que NO se hace (YAGNI)

- RAG / base vectorial para el contexto (un resumen alcanza para un proyecto).
- Fine-tuning del ASR.
- Cambiar de motor (Whisper/Canary) — parakeet se queda; el boosting nativo cubre la precisión.
- Persistencia en base de datos del historial del panel (acumular en memoria de la sesión basta).

## Orden de implementación

1. **Fase A** (A1 + A2) — independientes entre sí, ambas de bajo riesgo.
2. **Fase B** — el grueso; introduce `context.py` y unifica prompts.
3. **Fase C** — C1 y el de-risk de C2 primero; integrar boosting solo si el de-risk confirma; C3 solo si hace falta.
