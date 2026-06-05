# Panel lateral de respuestas a pedido + botón pausar captura

Fecha: 2026-06-04

## Problema

Al tocar los botones rápidos (💡 Ideas, 📝 Resumen, ❓ ¿Qué pregunto?, 🙋 Responder) o
usar el cuadro "Pregúntale a Claude", la respuesta vuelve como evento `suggestion` y se
pinta en `self.suggestion` (`ui/native.py`) — la **misma** tarjeta que usa el copiloto
proactivo. Como `is_question_for_me` corre continuamente sobre los **parciales** del audio
(`run.py:main`), a los pocos segundos una sugerencia proactiva **sobrescribe** la respuesta
que el usuario pidió a propósito. Síntoma: "la respuesta se mantiene unos segundos y se quita".

Además se quiere un botón para **pausar la captura** (p.ej. durante algo privado) y reanudarla.

## Decisiones (validadas con el usuario)

1. **Panel lateral con pestañas** para las respuestas a pedido (no ventana aparte ni pila de
   historial): mantiene todo en una sola ventana, clave en Wayland.
2. **Comportamiento de pestañas:** pestaña vacía → dispara la consulta al tocarla; pestaña con
   contenido → solo la muestra (no re-consulta); botón `🔄` re-consulta la pestaña actual.
3. **Pausa = "ignorar":** `pw-record` y NeMo siguen vivos; al pausar se descartan los
   parciales/finales (no se transcribe, no entra al contexto, no se manda a Claude). Reanudar
   es instantáneo y sin riesgo (no se reinicia el stream ni los hilos del transcriptor, que
   son frágiles según el CLAUDE.md).

## Diseño

### A) Separar flujos de respuesta

- La tarjeta `💡 sugerencia` inferior queda **solo** para lo proactivo (automático).
- Las respuestas de botones/cuadro van al **panel lateral persistente**, que nunca se
  sobrescribe solo.

### B) Contrato (`events.py`)

- `AskCommand` gana campo opcional `tab: str = ""` (`ideas|resumen|pregunto|respondo|libre`).
- Evento nuevo `Answer{ type:"answer", tab:str, text:str, ready:bool=True }`. El server
  responde los `ask` con `Answer` (no `Suggestion`). Las proactivas siguen con `Suggestion`.
- Comando cliente nuevo `CaptureCommand{ type:"capture", paused:bool }`. `parse_client_event`
  lo reconoce; `ClientEvent` lo incluye.

### C) Pausa (`server/app.py` + `run.py`)

- `create_app` crea `app.state.paused = threading.Event()` (no seteado = capturando).
- WS: al recibir `CaptureCommand`, setea/limpia el Event y **difunde**
  `Status(state="pausado"|"capturando")` a todas las UIs (sincroniza el botón).
- `run.py`: `on_partial`/`on_final` chequean `app.state.paused.is_set()` al inicio y
  retornan temprano si está pausado (antes de difundir, agregar a `ctx` o sugerir).

### D) Enrutado del `ask` (`server/app.py`)

- El WS responde el `AskCommand` con `Answer(tab=cmd.tab or "libre", text=answer)` en lugar
  de `Suggestion`. El estado sigue yendo a "pensando"/"capturando" salvo si está pausado
  (en pausa el estado se mantiene "pausado").

### E) UI nativa (`ui/native.py`)

- Cuerpo a 2 columnas (`QHBoxLayout`): izquierda = lo actual (insight, transcript, live,
  suggestion); derecha = **panel QA colapsable**.
- Panel QA: fila de pestañas `[💡 Ideas][📝 Resumen][❓ Pregunto][🙋 Respondo][💬]`,
  `QStackedWidget` con un `QTextEdit` de solo-lectura por pestaña, y acciones
  `[🔄 actualizar][copiar][✕ cerrar panel]`.
- Tocar una pestaña: muestra el panel y la selecciona. Vacía → manda `ask` con su `tab` y su
  prompt prearmado, muestra "pensando…". Con contenido → solo la muestra. `🔄` re-consulta la
  actual. `copiar` copia el texto de la pestaña activa al portapapeles. `✕` colapsa el panel.
- El cuadro inferior "Pregúntale a Claude" manda `ask` con `tab="libre"` → cae en `💬`.
- La ventana se ensancha al mostrar el panel (~820px) y vuelve a ~420 al colapsarlo.
- Botón `⏸`/`▶` en la barra superior (junto a `tema`/`limpiar`): al tocarlo manda
  `CaptureCommand`. El ícono y el estado se actualizan al recibir el `Status` por broadcast
  (no localmente), para quedar consistente entre UIs. Estado ámbar cuando pausado.
- Se elimina la fila vieja de botones rápidos de abajo (ahora son las pestañas).
- Estilos nuevos en los 4 `THEMES`: pestaña activa/inactiva, fondo del panel, color de pausa.

### F) Web (`ui/web/`)

Sin cambios por ahora (la nativa es la recomendada).

## Pruebas

Unitarias de lógica pura (en `.venv`, sin GPU/Claude):

- `Answer` serializa con `type:"answer"`, `tab`, `text`.
- `AskCommand` acepta `tab` opcional y default `""`.
- `parse_client_event` reconoce `{"type":"capture","paused":true}` → `CaptureCommand`.
- (Opcional) test de `server` que `ask` ahora responde un `answer` con el `tab` recibido.

Lo atado a Qt/GPU se valida ejecutando la app (de-risk "corre y observa"), como ya hace el
proyecto.

## Archivos

`src/asistente/events.py`, `src/asistente/server/app.py`, `src/asistente/ui/native.py`,
`run.py`, y tests en `tests/test_events.py` (+ quizá `tests/test_server.py`).
