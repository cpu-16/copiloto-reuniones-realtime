# Asistente de reuniones en tiempo real — Diseño

**Fecha:** 2026-06-03
**Estado:** Aprobado para planificación
**Autor:** Rafael (rvaldesgil@gmail.com) + Claude

## 1. Resumen

Asistente local que, durante una reunión virtual (Zoom, Google Meet, Teams, etc.),
**transcribe en vivo** lo que se habla y **sugiere respuestas con IA en tiempo real**.
Cuando al usuario le hacen una pregunta, la respuesta sugerida **ya está lista** (se
pre-genera de forma continua). Se muestra en una **ventanita flotante e interactiva**
que el usuario mueve donde quiera.

Todo corre en la máquina local del usuario. Solo el **texto** de la transcripción sale
hacia Claude (vía la suscripción de Claude Code); el audio nunca sale del equipo.

## 2. Objetivos y no-objetivos

### Objetivos
- Transcripción en vivo en español del audio de la reunión (lo que dicen los demás).
- Sugerencia de respuesta proactiva: cuando te preguntan, el borrador ya existe.
- Poder hacerle una pregunta puntual a la IA a demanda durante la reunión.
- Ventana flotante propia, sin bordes, siempre-encima, arrastrable y anclable.
- Privacidad: audio y transcripción se procesan localmente; solo texto va a Claude.

### No-objetivos (por ahora)
- Invisibilidad nativa ante la captura de pantalla en Linux (no existe la API; se
  resolverá por arquitectura en una fase posterior — ver §8 Fase 3).
- Auto-responder por el usuario (siempre es el usuario quien decide qué decir).
- Diarización avanzada / identificación de múltiples hablantes por voz (fase posterior).
- Soporte multiplataforma (el objetivo es Linux/Fedora del usuario).

## 3. Entorno objetivo (verificado)

- Fedora 44, kernel 7.0, Wayland probable.
- CPU i9-13950HX (32 hilos), 32 GB RAM.
- GPU NVIDIA RTX 4060 Laptop, 8 GB VRAM, driver 595.
- Audio: **PipeWire 1.6.6** (hay `pw-record`, `pw-cli`, `wpctl`; **no** hay `pactl`).
- Python 3.14.5 del sistema (demasiado nuevo) → usaremos un venv con **Python 3.12**.
- Node v24.14.1.
- `claude` CLI v2.1.162 disponible y autenticado con la suscripción.

## 4. Hallazgo crítico de latencia (medido)

`claude -p --model haiku` con la suscripción **funciona**, pero medimos **~6–9 s** por
respuesta en frío. Causas detectadas:
1. Un hook `SessionStart` inyecta mucho contexto (skills) en cada invocación.
2. Carga de herramientas/MCP innecesarias.
3. Sin un buen system prompt, Haiku pide aclaración en vez de responder.

**Consecuencia de diseño:** generar la respuesta *después* de detectar la pregunta es
demasiado lento. Por eso el sistema **mantiene contexto y pre-genera borradores de
forma continua**, y solo **muestra/promueve** el borrador cuando detecta una pregunta
dirigida al usuario. Además, el proceso Claude se mantiene **"caliente" y descafeinado**.

## 5. Arquitectura

```
[PipeWire monitor] → [Transcriptor Whisper] → [Orquestador FastAPI/WS] → [UI flotante]
   (pw-record)          (RealtimeSTT GPU)         │           ▲             ├─ pywebview
                                                  ▼           │             └─ PySide6
                                          [Claude -p caliente] │
                                          (borrador continuo)──┘
```

Cinco componentes, cada uno con una responsabilidad única y un contrato claro. El
orquestador es el único punto que conoce a todos; los demás se comunican por interfaces
bien definidas (stdout PCM, eventos WebSocket JSON, stdin/stdout stream-json).

### 5.1 Captura de audio (`capture/`)
- **Qué hace:** entrega audio PCM 16 kHz mono del *monitor* del sink de salida (lo que
  suena = los demás participantes).
- **Cómo:** `pw-record --target <node-id-monitor> --rate 16000 --channels 1 --format s16 -`
  hacia stdout, leído por el transcriptor.
- **Depende de:** PipeWire. El node-id del monitor se descubre con `pw-record --list-targets` / `wpctl status`.
- Fase 1: solo audio del sistema. El micrófono del usuario se agrega en fase posterior
  (segundo stream etiquetado "Yo").

### 5.2 Transcriptor (`transcribe/`)
- **Qué hace:** convierte el PCM en texto; emite parciales (tentativos, ~0.5 s) y frases
  finales estabilizadas (~1.5–3 s).
- **Cómo:** **RealtimeSTT** (`AudioToTextRecorder`, `use_microphone=False`, alimentado por
  `feed_audio()`) sobre **faster-whisper** modelo **`turbo`** (large-v3-turbo, multilingüe),
  `device="cuda"`, `compute_type="float16"`, `language="es"`, VAD Silero.
- **Depende de:** CUDA 12 + cuDNN 9 vía pip (`nvidia-cublas-cu12`, `nvidia-cudnn-cu12`),
  venv Python 3.12.
- **Salida:** eventos `{type: "partial"|"final", text, ts}` al orquestador (cola interna).
- Nota: `turbo` (no `distil-*`, que es solo inglés).

### 5.3 Orquestador (`server/`)
- **Qué hace:** corazón del sistema. Mantiene el estado de la reunión y coordina todo.
- **Responsabilidades:**
  - Mantiene un buffer rodante del transcript (contexto de los últimos N segundos/turnos).
  - Hace *push* de la transcripción a las UIs por WebSocket.
  - **Detección de "me preguntan a mí":** capa híbrida — heurística barata (nombre del
    usuario configurable, patrones como "¿tú qué opinas?", "¿puedes…?", signo de pregunta
    + pausa) y un clasificador ligero (Claude Haiku con prompt mínimo) que etiqueta el
    último tramo como `pregunta_directa` / `pregunta_general` / `ignorar`.
  - **Borrador continuo:** alimenta el contexto a Claude y mantiene un borrador de
    respuesta actualizado; cuando se detecta pregunta directa, **promueve** el borrador a
    la tarjeta de "respuesta sugerida".
  - Atiende el comando manual "pregúntale a Claude sobre esto".
- **Cómo:** FastAPI + WebSocket. Token de acceso para la UI (transcript sensible).
- **Depende de:** transcriptor (entrada), cliente Claude (§5.4), UIs (salida).

### 5.4 Cerebro Claude (`brain/`)
- **Qué hace:** genera borradores/respuestas sugeridas en español a partir del contexto.
- **Cómo:** proceso **`claude -p` persistente** con `--input-format stream-json
  --output-format stream-json` (sesión caliente, se le van enviando mensajes sin re-arrancar).
  **Configuración descafeinada** para minimizar latencia:
  - Modelo **Haiku** (`--model haiku`).
  - Sin hooks (settings limpio / `--settings` apuntando a config vacía), sin MCP
    (`--strict-mcp-config` sin servidores), sin herramientas (`--disallowed-tools` o
    `--allowed-tools` vacío), `--max-turns 1`.
  - **System prompt mínimo** que ordena: responder siempre con una sugerencia corta y
    accionable en español, nunca pedir aclaración, tono natural del usuario.
- **Depende de:** CLI `claude` autenticado con la suscripción.
- **Objetivo de latencia (Fase 0):** primer token < 3 s con sesión caliente + stripped.
  Si no se logra de forma estable, el fallback es API key de Anthropic (documentado pero
  no preferido) — esto se decide tras medir en Fase 0.

### 5.5 UI flotante (`ui/`)
Dos clientes delgados sobre el **mismo contrato WebSocket** (no se duplica el motor):

- **`ui/web/`** — HTML/JS servido por el orquestador, mostrado dentro de una ventana
  nativa con **pywebview** (`frameless=True`, `on_top=True`, `easy_drag=True`).
  Reutilizable tal cual en el celular (Fase 3) abriendo la misma URL por LAN.
- **`ui/native/`** — widget **PySide6/Qt** que consume el mismo WebSocket y renderiza
  nativo (transparencia, atajos globales).

El usuario probará ambas y elegirá. Funciones de ventana: arrastrar, anclar/fijar
posición, ajustar opacidad, atajo mostrar/ocultar. Contenido: columna de transcripción
en vivo + tarjeta destacada "💡 respuesta sugerida" + caja para preguntar a demanda.

### 5.6 Contrato WebSocket (borrador)
Eventos servidor→UI: `transcript.partial`, `transcript.final`, `suggestion.draft`
(borrador en progreso, streaming), `suggestion.ready` (pregunta directa detectada),
`status`. Eventos UI→servidor: `ask` (pregunta manual), `clear`, `config`.

## 6. Flujo de datos

1. `pw-record` emite PCM del monitor → RealtimeSTT.
2. RealtimeSTT emite parciales/finales → orquestador (push a UI como `transcript.*`).
3. Orquestador alimenta el contexto rodante a Claude caliente → recibe borrador en
   streaming → push como `suggestion.draft`.
4. Detector marca pregunta directa → orquestador promueve borrador como `suggestion.ready`.
5. UI muestra transcript + tarjeta de sugerencia; el usuario decide si la usa.
6. (A demanda) usuario escribe `ask` → orquestador consulta a Claude → respuesta a la UI.

## 7. Manejo de errores y bordes

- **Claude lento/cae:** la transcripción nunca se bloquea por Claude (caminos
  independientes). Si Claude tarda > umbral, la UI muestra "pensando…" y conserva el
  último borrador. Reinicio automático del proceso si muere.
- **Audio sin señal / sink equivocado:** la UI muestra estado de captura; selector de
  fuente (node-id) configurable. Validación temprana con Zoom/Meet/Teams en Fase 0.
- **VRAM:** `turbo` ~4 GB deja margen en 8 GB; si se agrega segundo stream (mic), bajar a
  `int8_float16` o `medium`.
- **Falsos positivos de "me preguntan":** umbral de confianza; el borrador se muestra
  como sugerencia, nunca se actúa solo.
- **Seguridad:** UI tras token de acceso local; nada se expone fuera de localhost/LAN
  controlada.

## 8. Plan por fases

- **Fase 0 — De-risk (medible):**
  - Optimizar y medir latencia de Claude caliente + descafeinado (objetivo 1er token < 3 s).
  - Validar captura PipeWire del monitor con Zoom, Meet y Teams reales.
  - Confirmar venv Python 3.12 + faster-whisper `turbo` en GPU.
- **Fase 1 — MVP:** captura → transcripción en vivo en la UI flotante (pywebview) +
  botón manual "pregúntale a Claude". Contrato WebSocket estable.
- **Fase 2 — Proactivo:** borrador continuo + detección de pregunta dirigida → sugerencia
  lista al instante. Segunda UI (PySide6) para comparar.
- **Fase 3 — Ocultar + extras:** abrir la misma UI web en celular/2ª pantalla
  (invisibilidad real); opcional micrófono + etiqueta de hablante ("Yo"/"Otros") y
  minuta/resumen al final.

## 9. Stack y dependencias

- **Lenguaje base:** Python 3.12 (venv). Node disponible si alguna UI lo requiere.
- **Audio:** PipeWire (`pw-record`), sin instalar `pipewire-pulse`.
- **STT:** `RealtimeSTT`, `faster-whisper`, `nvidia-cublas-cu12`, `nvidia-cudnn-cu12`.
- **Servidor:** `fastapi`, `uvicorn`, `websockets`.
- **UI:** `pywebview` (web) y `PySide6` (nativa).
- **IA:** CLI `claude` (suscripción), modo `-p` stream-json, modelo Haiku.
- **Licencias:** proyecto propio; los OSS revisados (Pluely/Glass/Natively son GPL/AGPL)
  se usan solo como **referencia de ideas**, no se copia código copyleft.

## 10. Referencias de proyectos OSS (solo inspiración)

- **Pluely** (Tauri, Linux, Whisper+Claude BYOK) — referencia de UI/flujo BYOK.
- **Glass (Pickle)** — referencia de separación mic/sistema con AEC.
- **Natively** — referencia de RAG local y manejo de audio nativo.
- Confirmado por la investigación: **ninguno** resuelve invisibilidad en Linux por
  software; todos dependerían igual de "segundo dispositivo".

## 11. Riesgos principales

1. **Latencia de Claude vía CLI** (mayor riesgo) → mitigado con proceso caliente,
   config descafeinada, borrador continuo; fallback a API key si Fase 0 lo exige.
2. **Detección fiable de "me preguntan a mí"** → híbrido heurística + clasificador,
   umbral, mostrar como sugerencia (nunca auto-actuar).
3. **Estabilidad de captura PipeWire entre apps** → validar temprano con cada plataforma.
4. **Python 3.14 del sistema** → aislar con venv 3.12.
