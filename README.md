# 🎙️ Copiloto de Reuniones en Tiempo Real

<div align="center">

![Python](https://img.shields.io/badge/Python-3.12-3776AB?style=for-the-badge&logo=python&logoColor=white)
![NVIDIA Nemotron](https://img.shields.io/badge/NVIDIA-Nemotron_3.5_ASR-76B900?style=for-the-badge&logo=nvidia&logoColor=white)
![NeMo](https://img.shields.io/badge/NeMo-Streaming_ASR-76B900?style=for-the-badge)
![Claude](https://img.shields.io/badge/Claude-Copilot-D97757?style=for-the-badge&logo=anthropic&logoColor=white)
![FastAPI](https://img.shields.io/badge/FastAPI-WebSocket-009688?style=for-the-badge&logo=fastapi&logoColor=white)
![PySide6](https://img.shields.io/badge/PySide6-Overlay-41CD52?style=for-the-badge&logo=qt&logoColor=white)
![Local](https://img.shields.io/badge/100%25-Local-111111?style=for-the-badge)

**Transcribe tus reuniones en vivo en la GPU y te sugiere qué responder — todo local, en una ventanita flotante que vive encima de cualquier app.**

[Demo](#demo) · [Cómo funciona](#cómo-funciona) · [Motores ASR](#motores-de-transcripción) · [Inicio rápido](#inicio-rápido) · [Configuración](#configuración) · [Privacidad](#privacidad)

</div>

---

## Demo

<div align="center">

**🎬 Video demo en camino**

</div>

<!--
  ▶ PARA AÑADIR EL VIDEO (con play/pausa):
  Edita este README en GitHub (botón ✏️) y ARRASTRA tu .mp4/.mov justo aquí.
  GitHub lo sube y genera una URL https://github.com/user-attachments/assets/...
  que se reproduce con CONTROLES. Reemplaza el bloque de arriba por esa URL (sola),
  o por una de estas líneas:

  <video src="https://github.com/user-attachments/assets/TU-VIDEO" controls width="100%"></video>
  <video src="docs/images/demo.mp4" controls width="100%"></video>   (si commiteas el mp4)
  <img src="docs/images/demo.gif" width="100%">                       (gif: autoplay, sin controles)
-->

> En el demo se ve: transcripción bilingüe en vivo, el panel 🧠 con resumen/ideas/alerta del copiloto, la detección de "¿me preguntan a mí?" con respuesta sugerida al instante, y el panel lateral de respuestas a pedido.

---

## Cómo funciona

Es un **copiloto de reuniones que corre 100% en tu máquina**. Captura el audio del sistema (lo que suena en una llamada de Meet, Zoom, WhatsApp, etc.), lo **transcribe en vivo en la GPU**, y usa **Claude** (vía tu suscripción, sin API key) para:

- 🧠 **Entender el hilo** — cada pocos segundos arma un resumen + ideas para aportar + una alerta si te asignan una tarea.
- 🙋 **Responder por ti** — detecta cuándo te hacen una pregunta a *ti* (por tu nombre o en segunda persona) y te prepara una respuesta con el contexto de la reunión.
- 💬 **Responder a pedido** — botones para pedir *ideas, resumen, qué preguntar o cómo responder*, o una caja para preguntarle lo que sea sobre la reunión.

Todo en una **ventana flotante, sin marco y siempre encima**, que arrastras donde quieras.

> Pensado para **Fedora + Wayland + NVIDIA**. El audio nunca sale de tu equipo: solo el **texto** de la transcripción viaja a Claude.

---

## La ventana por dentro

Una sola ventana flotante reúne todo. Así se reparte:

<!-- Captura: sube una LIMPIA (sin datos de cliente) como docs/images/screenshot-ventana.png
     y descomenta la línea de abajo:
<div align="center">
<img src="docs/images/screenshot-ventana.png" alt="Ventana nativa del copiloto" width="85%">
</div>
-->

```
┌──────────────────────────────────────────────────────────────────┐
│  capturando            ⏸ pausar · tema · limpiar · – · ⤢ · ✕      │  barra superior
├──────────────────────────────────────┬───────────────────────────┤
│  PANEL DEL COPILOTO 🧠                │  PESTAÑAS  💡 📝 ❓ 🙋 💬 📋 │  panel lateral
│  resumen · ideas · alerta            │                           │  (respuestas
│                                      │   Respuestas a pedido      │   a pedido)
│  TRANSCRIPCIÓN EN VIVO                │   con historial + hora     │
│  (negrita = frase confirmada)        │                           │
│  ...parcial en cursiva mientras hablas│   🔄 actualizar · 💾 ctx   │
│ ┌──────────────────────────────────┐ │   🧹 limpiar · copiar · ✕  │
│ │ 💡 Respuesta sugerida            │ │                           │
│ └──────────────────────────────────┘ │                           │
├──────────────────────────────────────┴───────────────────────────┤
│  [ 💡 Ideas ] [ 📝 Resumen ] [ ❓ ¿Qué pregunto? ] [ 🙋 Responder ] │  acciones rápidas
├──────────────────────────────────────────────────────────────────┤
│  [ Pregúntale a Claude sobre la reunión… ]            [ Preguntar ]│  caja de preguntas
└──────────────────────────────────────────────────────────────────┘
```

- **Barra superior** — el **estado** (capturando · pensando · pausado · error) y los controles: **⏸ pausar** la captura (descarta el audio sin cerrar nada), **tema** (cicla oscuro · claro · vidrio · vidrio legible), **limpiar** la transcripción, **–** minimizar, **⤢** expandir, **✕** cerrar (mata el proceso).
- **Panel del copiloto 🧠** — cada `interval_s` segundos: una línea de **resumen** de lo que se habla, **ideas** para aportar, y una **alerta** si te asignan una tarea o se toma una decisión.
- **Transcripción en vivo** — las **frases confirmadas** (con auto-scroll); el **parcial** va en cursiva mientras alguien habla.
- **💡 Respuesta sugerida** — aparece **sola** cuando detecta que te preguntan a *ti* (por tu nombre o en segunda persona).
- **Panel lateral de respuestas a pedido** — pestañas **💡 Ideas · 📝 Resumen · ❓ Preguntas · 🙋 Responder · 💬 Pregunta libre · 📋 Contexto** (esta última es editable: escribes el *briefing* de la sesión). Las respuestas se **acumulan con su hora** (historial, no se pisan). Acciones: **🔄 actualizar**, **💾 guardar contexto**, **🧹 limpiar**, **copiar**, **✕** cerrar el panel.
- **Acciones rápidas** — un toque pide *ideas / resumen / qué preguntar / cómo responder* al instante.
- **Caja de preguntas** — escríbele lo que sea; Claude responde con el contexto de la reunión.

---

## Arquitectura

Pipeline de 5 piezas desacopladas; `run.py` es el ensamblador que las cablea:

```
   PipeWire (monitor del sink)
            │  PCM s16 mono 16k
            ▼
   Transcriptor ASR (GPU)  ──parciales/finales──►  Orquestador (FastAPI + WebSocket)
   Nemotron / Parakeet / Whisper                          │              ▲
                                                          ▼              │ eventos JSON
                                            Cerebro Claude (claude -p caliente)
                                                          │
                                                          ▼
                                          UI flotante (PySide6 nativa / web)
```

- **Captura** · `pw-record` entrega chunks PCM del monitor del sink.
- **Transcripción** · streaming cache-aware en la GPU (mismo interfaz para los 3 motores).
- **Orquestador** · sirve la UI, expone `/ws` (token), difunde eventos y mantiene el **contexto de sesión en 3 capas** (briefing durable + resumen acumulativo + ventana rodante).
- **Cerebro** · un proceso `claude -p` **persistente y precalentado** (TTFT ~2-3 s).
- **UI** · widget nativo PySide6 (estable en Wayland vía XWayland), con temas, panel lateral y caja de preguntas.

---

## Motores de transcripción

Tres motores ASR, cada uno en su propio venv (sus dependencias de `torch`/NeMo chocan). Se elige con `engine` en `config.toml` o con `--engine`:

| Motor | Modelo | VRAM | Latencia | Idiomas | Estado |
|-------|--------|------|----------|---------|--------|
| **`nemotron`** ⭐ | [Nemotron 3.5 ASR streaming 0.6B](https://huggingface.co/nvidia/nemotron-3.5-asr-streaming-0.6b) | ~2.7 GB | **Baja** (streaming cache-aware nativo) | es/en + 17 (detección por frase) | Recomendado |
| **`parakeet`** | [Parakeet TDT 0.6B v3](https://huggingface.co/nvidia/parakeet-tdt-0.6b-v3) | ~1.3 GB | Media | es/en + 23 | Respaldo liviano |
| **`whisper`** | faster-whisper `turbo` | ~2.9 GB | Media | es/en | Alternativa |

**¿Por qué Nemotron?** Es un **RNN-T FastConformer cache-aware**: hace *streaming de verdad* (no re-transcribe el buffer), con baja latencia y muy buen español (WER 4.11% en FLEURS). Detecta **español ↔ inglés** automáticamente por frase — ideal para reuniones donde se mezclan idiomas y términos técnicos.

---

## Características

- 🌗 **Bilingüe automático** — `target_lang = "auto"` detecta es/en sin que hagas nada.
- 📋 **Contexto que no se pierde** — un *briefing* de sesión (escribes de qué va la reunión, o cargas un archivo/proyecto), un *resumen acumulativo* que mantiene el hilo entre temas, y la ventana de lo más reciente. El copiloto no pierde el foco aunque la llamada salte de tema.
- 📚 **Glosario** — corrige nombres propios y términos técnicos del proyecto (`Proxmox`, `Cloudflare`, `pfSense`…) que el ASR oye raro.
- 🎨 **Temas legibles** — oscuro, claro y dos modos vidrio; la ventana se mantiene legible aunque esté semitransparente.
- ⏸️ **Pausar captura** · 🧹 **limpiar** · arrastrar · minimizar · expandir.
- 🔒 **Atajo global** (GNOME) para mostrar/ocultar la ventana al vuelo.

---

## Inicio rápido

> **Requisitos:** Fedora con PipeWire, GPU NVIDIA, Python 3.12, [`uv`](https://github.com/astral-sh/uv) y el CLI `claude` autenticado.

**1) Motor recomendado — Nemotron (`.venv-nemotron`):**
```bash
uv venv .venv-nemotron
uv pip install --python .venv-nemotron "nemo_toolkit[asr] @ git+https://github.com/NVIDIA/NeMo.git@main"
uv pip install --python .venv-nemotron "fastapi>=0.115" "uvicorn[standard]" websockets \
    "pydantic>=2.7" pywebview PySide6 qtpy
uv pip install --python .venv-nemotron -e . --no-deps
```

**2) Configura:**
```bash
cp config.example.toml config.toml      # edítalo (token, idioma, glosario…)
.venv-nemotron/bin/python scripts/derisk_audio.py --list   # encuentra el monitor del sink
# pon ese node-id en  [audio] target  de config.toml
```

**3) Corre:**
```bash
.venv-nemotron/bin/python run.py --native
```

La primera vez descarga el modelo (~2.4 GB). Cambiar de motor es solo el comando:
```bash
.venv-parakeet/bin/python run.py --native --engine parakeet
.venv/bin/python            run.py --native --engine whisper
```

<details>
<summary>Instalar los motores de respaldo (Parakeet / Whisper)</summary>

```bash
# Whisper (.venv)
python3.12 -m venv .venv && source .venv/bin/activate && pip install -e ".[dev]"

# Parakeet (.venv-parakeet, NeMo 2.7.x)
uv venv .venv-parakeet --python 3.12
uv pip install --python .venv-parakeet "nemo_toolkit[asr]" fastapi "uvicorn[standard]" \
    websockets "pydantic>=2.7" pywebview PySide6 qtpy setuptools
uv pip install --python .venv-parakeet -e . --no-deps
```
</details>

---

## Configuración

Todo vive en `config.toml` (copia de `config.example.toml`, gitignorado). Las perillas principales:

| Sección | Clave | Qué hace |
|---------|-------|----------|
| raíz | `engine` | `"nemotron"` · `"parakeet"` · `"whisper"` |
| `[user]` | `names`, `role` | tus nombres (para detectar preguntas) y tu rol (personaliza la IA) |
| `[nemotron]` | `target_lang` | `"auto"` (es/en) o `"es"` para forzar español |
| `[nemotron]` | `att_context_size` | `[56,13]`=1120 ms (más preciso) … `[56,3]`=320 ms (más rápido) |
| `[asr]` | `glossary` | términos/nombres del proyecto para corregir la transcripción |
| `[context]` | `briefing`, `briefing_file` | contexto durable: texto fijo o un archivo/carpeta que se resume al arrancar |
| `[copilot]` | `interval_s` | cada cuántos segundos el copiloto analiza el contexto |
| `[audio]` | `target` | node-id del monitor del sink (de `derisk_audio.py --list`) |
| `[parakeet]` | `silence_rms` | umbral de voz; `0` = autocalibra el piso de ruido |
| `[server]` | `token` | token de acceso a la UI (**cámbialo**) |

---

## Privacidad

- **El audio nunca sale de tu equipo.** La captura y la transcripción ocurren localmente en tu GPU.
- A Claude solo viaja el **texto** de la transcripción reciente, para las sugerencias.
- La UI está protegida por token y escucha solo en `127.0.0.1`.
- Tu `config.toml` (token, glosario, rutas) está **gitignorado** — nunca se sube.

---

## Lecciones aprendidas (gotchas)

Algunas decisiones de diseño que costaron y quedaron documentadas:

- **`claude -p` en frío tarda 5-9 s** → se usa **caliente** (proceso persistente + prewarm) y stripped; TTFT baja a ~2-3 s.
- **Nemotron es "con prompt"** → hay que fijar el idioma con `set_inference_prompt(...)` o decodifica vacío.
- **Streaming sin comerse palabras** → usar `CacheAwareStreamingAudioBuffer` de NeMo (preprocesa una vez) en vez de re-preprocesar ventanas, y consumir solo chunks completos.
- **Sesiones largas** → el RNN-T acumula la hipótesis sin límite; se reinicia por frase/longitud (manteniendo el cache acústico) para no ralentizarse.
- **Wayland** → la ventana nativa fuerza XWayland (`QT_QPA_PLATFORM=xcb`) para que frameless/always-on-top/arrastre sean fiables.

---

## Roadmap

- [ ] Phrase boosting nativo de NeMo (sesgar el decoder con el glosario, no solo corrección por similitud).
- [ ] Modo fp16 para Nemotron (bajar VRAM a ~1.4 GB).
- [ ] UI en un segundo dispositivo para ocultarla al compartir pantalla.
- [ ] Reciclaje del buffer de audio en maratones de varias horas.

---

<div align="center">

Hecho con ☕ en 🇵🇦 · Procesamiento local · Tu audio es tuyo

</div>
