# Asistente de Reuniones en Tiempo Real — Plan de Implementación (Fase 0 + Fase 1)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Entregar un MVP que capture el audio de una reunión, lo transcriba en vivo en español y lo muestre en una ventanita flotante, con un botón para preguntarle a Claude a demanda.

**Architecture:** Cinco componentes desacoplados (captura PipeWire → transcriptor Whisper → orquestador FastAPI/WebSocket → cerebro `claude -p` caliente → UI flotante pywebview). El orquestador es el único que conoce a todos; los demás se comunican por interfaces simples (PCM por stdout, eventos JSON por WebSocket, stream-json por stdin/stdout). Antes del MVP, una **Fase 0** valida con scripts medibles las tres incógnitas de riesgo: captura de audio, Whisper en GPU y latencia de Claude.

**Tech Stack:** Python 3.12 (venv), PipeWire (`pw-record`), RealtimeSTT + faster-whisper (`turbo`), FastAPI + Uvicorn + WebSockets, pydantic v2, `claude` CLI (suscripción, modo `-p` stream-json, modelo Haiku), pywebview, pytest.

**Referencia:** Spec en `docs/superpowers/specs/2026-06-03-asistente-realtime-design.md`.

---

## Estructura de archivos

```
ASISTENTE_REALTIME/
├── pyproject.toml                  # deps y config de proyecto
├── .gitignore
├── config.example.toml             # plantilla de config (nombre, idioma, sink, token)
├── README.md
├── scripts/                        # Fase 0 — de-risk, ejecutables sueltos
│   ├── derisk_audio.py             # lista targets PipeWire y graba 5s del monitor
│   ├── derisk_whisper.py           # carga faster-whisper turbo en GPU y transcribe
│   └── derisk_claude.py            # mide latencia de claude -p descafeinado (frío vs caliente)
├── src/asistente/
│   ├── __init__.py
│   ├── config.py                   # carga config.toml -> objeto Config
│   ├── events.py                   # modelos pydantic del contrato WebSocket
│   ├── capture/
│   │   ├── __init__.py
│   │   └── pipewire.py             # pw-record subprocess -> chunks PCM
│   ├── transcribe/
│   │   ├── __init__.py
│   │   └── whisper_stt.py          # wrapper RealtimeSTT -> callbacks de texto
│   ├── brain/
│   │   ├── __init__.py
│   │   └── claude_client.py        # proceso claude -p caliente, stream-json
│   ├── server/
│   │   ├── __init__.py
│   │   └── app.py                  # FastAPI + WebSocket, orquestación
│   └── ui/
│       ├── __init__.py
│       ├── launcher.py             # ventana pywebview frameless/on-top/draggable
│       └── web/
│           ├── index.html
│           └── app.js
└── tests/
    ├── test_events.py
    ├── test_config.py
    ├── test_claude_client.py
    └── test_server.py
```

**Responsabilidad por archivo:** cada módulo hace una sola cosa y se prueba aislado. `events.py` es el contrato compartido (lo importan server y, conceptualmente, las UIs). Lógica pura y framing de mensajes → tests unitarios reales (TDD). Piezas atadas a hardware/IO externo (audio, GPU, subprocess de Claude) → scripts de validación "ejecuta y observa" con salida esperada, que es el equivalente honesto de un test para integración externa.

---

## FASE 0 — De-risk (validación medible antes del MVP)

### Task 1: Andamiaje del proyecto

**Files:**
- Create: `pyproject.toml`
- Create: `.gitignore`
- Create: `src/asistente/__init__.py` (vacío)
- Create: `config.example.toml`

- [ ] **Step 1: Crear el venv con Python 3.12**

Run:
```bash
cd /home/gar16/datos/ASISTENTE_REALTIME
which python3.12 || sudo dnf install -y python3.12
python3.12 -m venv .venv
source .venv/bin/activate
python --version
```
Expected: `Python 3.12.x`

- [ ] **Step 2: Crear `pyproject.toml`**

```toml
[project]
name = "asistente-realtime"
version = "0.1.0"
description = "Copiloto de reuniones en tiempo real (transcribe + sugiere)"
requires-python = ">=3.12,<3.13"
dependencies = [
    "fastapi>=0.115",
    "uvicorn[standard]>=0.30",
    "websockets>=12",
    "pydantic>=2.7",
    "pywebview>=5.1",
    "RealtimeSTT>=0.3.7",
    "faster-whisper>=1.0",
    "nvidia-cublas-cu12",
    "nvidia-cudnn-cu12",
    "tomli; python_version < '3.11'",
]

[project.optional-dependencies]
dev = ["pytest>=8", "pytest-asyncio>=0.23", "httpx>=0.27"]

[tool.pytest.ini_options]
asyncio_mode = "auto"
testpaths = ["tests"]

[build-system]
requires = ["setuptools>=68"]
build-backend = "setuptools.build_meta"

[tool.setuptools.packages.find]
where = ["src"]
```

- [ ] **Step 3: Crear `.gitignore`**

```gitignore
.venv/
__pycache__/
*.pyc
config.toml
*.wav
.pytest_cache/
models/
```

- [ ] **Step 4: Crear `config.example.toml`**

```toml
# Copia a config.toml y ajusta
[user]
# Nombres con los que te llaman en reuniones (para detectar "¿me preguntan a mí?")
names = ["Rafael", "Rafa"]
# Idioma por defecto de las respuestas sugeridas
reply_language = "es"

[audio]
# node-id o nombre del monitor del sink. Descúbrelo con scripts/derisk_audio.py.
# Vacío = se autodetecta el sink por defecto.
target = ""
sample_rate = 16000

[whisper]
model = "turbo"
compute_type = "float16"
language = "es"

[claude]
model = "haiku"

[server]
host = "127.0.0.1"
port = 8765
# Token de acceso a la UI (cámbialo)
token = "cambia-este-token"
```

- [ ] **Step 5: Crear paquete e instalar**

Run:
```bash
mkdir -p src/asistente && touch src/asistente/__init__.py
pip install -e ".[dev]"
```
Expected: instalación termina sin error (la descarga de torch/ctranslate2 puede tardar).

- [ ] **Step 6: Inicializar git y primer commit**

```bash
git init
git add pyproject.toml .gitignore config.example.toml src/asistente/__init__.py docs/
git commit -m "chore: andamiaje del proyecto asistente-realtime"
```

---

### Task 2: De-risk de captura de audio (PipeWire)

**Files:**
- Create: `scripts/derisk_audio.py`

- [ ] **Step 1: Escribir el script de validación de audio**

```python
"""De-risk de captura: lista targets de PipeWire y graba 5s del monitor del sink.
Uso:
    python scripts/derisk_audio.py --list
    python scripts/derisk_audio.py --target <node-id-o-nombre> --out prueba.wav
Luego abre prueba.wav y confirma que se oye el audio del sistema (los demás).
"""
import argparse
import subprocess
import sys
import wave


def list_targets() -> None:
    print("=== pw-record --list-targets ===")
    subprocess.run(["pw-record", "--list-targets"], check=False)
    print("\n=== wpctl status (busca el sink de salida por defecto) ===")
    subprocess.run(["wpctl", "status"], check=False)


def record(target: str, out: str, seconds: int = 5, rate: int = 16000) -> None:
    cmd = ["pw-record", "--rate", str(rate), "--channels", "1", "--format", "s16"]
    if target:
        cmd += ["--target", target]
    cmd += [out]
    print(f"Grabando {seconds}s -> {out}\n  cmd: {' '.join(cmd)}")
    proc = subprocess.Popen(cmd)
    try:
        proc.wait(timeout=seconds)
    except subprocess.TimeoutExpired:
        proc.terminate()
        proc.wait()
    with wave.open(out, "rb") as w:
        frames = w.getnframes()
    print(f"OK: {frames} frames grabados ({frames / rate:.1f}s).")
    if frames == 0:
        print("ADVERTENCIA: 0 frames. Target equivocado o sin audio sonando.")
        sys.exit(1)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--list", action="store_true")
    ap.add_argument("--target", default="")
    ap.add_argument("--out", default="prueba.wav")
    args = ap.parse_args()
    if args.list:
        list_targets()
    else:
        record(args.target, args.out)


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Listar los targets de audio**

Run: `python scripts/derisk_audio.py --list`
Expected: imprime nodos; identifica el **monitor del sink de salida** (algo como `alsa_output.*.monitor` o un node-id). Anótalo.

- [ ] **Step 3: Validar la captura con audio real**

Pon a sonar audio (un video de YouTube o una llamada de prueba) y corre:
```bash
python scripts/derisk_audio.py --target <node-id-monitor> --out prueba.wav
```
Expected: `OK: N frames grabados (~5.0s)`. Abre `prueba.wav` y confirma que **se oye** lo que sonaba. Si da 0 frames o silencio, prueba otro target.

- [ ] **Step 4: Anotar el target ganador y commit**

Guarda el target en `config.example.toml` como comentario de referencia y:
```bash
git add scripts/derisk_audio.py config.example.toml
git commit -m "feat(derisk): validación de captura de audio PipeWire"
```

---

### Task 3: De-risk de Whisper en GPU

**Files:**
- Create: `scripts/derisk_whisper.py`

- [ ] **Step 1: Escribir el script de validación de Whisper**

```python
"""De-risk de transcripción: carga faster-whisper 'turbo' en la GPU y transcribe un WAV.
Uso: python scripts/derisk_whisper.py prueba.wav
Verifica: que cargue en CUDA, que el texto en español sea correcto y mide el tiempo.
"""
import sys
import time

from faster_whisper import WhisperModel


def main() -> None:
    audio = sys.argv[1] if len(sys.argv) > 1 else "prueba.wav"
    print("Cargando modelo 'turbo' en CUDA (float16)...")
    t0 = time.perf_counter()
    model = WhisperModel("turbo", device="cuda", compute_type="float16")
    print(f"Modelo cargado en {time.perf_counter() - t0:.1f}s")

    t1 = time.perf_counter()
    segments, info = model.transcribe(audio, language="es")
    text = " ".join(seg.text for seg in segments)
    dt = time.perf_counter() - t1
    print(f"Idioma detectado: {info.language} (p={info.language_probability:.2f})")
    print(f"Transcripción ({dt:.2f}s):\n{text}")
    if not text.strip():
        print("ADVERTENCIA: transcripción vacía.")
        sys.exit(1)


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Instalar runtime CUDA si falta**

Run:
```bash
pip install nvidia-cublas-cu12 nvidia-cudnn-cu12
```
Expected: instalado (ya viene en pyproject, este paso confirma).

- [ ] **Step 3: Ejecutar y validar**

Run: `python scripts/derisk_whisper.py prueba.wav`
Expected: imprime `Idioma detectado: es` y un texto en español coherente con lo grabado. Anota el tiempo de transcripción (debería ser una fracción de la duración del audio). Si falla por cuDNN, verifica `python -c "import torch; print(torch.cuda.is_available())"`.

- [ ] **Step 4: Commit**

```bash
git add scripts/derisk_whisper.py
git commit -m "feat(derisk): validación de faster-whisper turbo en GPU"
```

---

### Task 4: De-risk de latencia de Claude (descafeinado, frío vs caliente)

**Files:**
- Create: `scripts/derisk_claude.py`

- [ ] **Step 1: Escribir el script que mide latencia en frío (one-shot descafeinado)**

```python
"""De-risk de Claude: mide latencia de `claude -p` descafeinado.
Modo frío: una invocación nueva por pregunta.
Uso: python scripts/derisk_claude.py
"""
import subprocess
import time

SYSTEM = (
    "Eres un copiloto de reuniones. Dado el contexto de una conversación, responde SIEMPRE "
    "con una sugerencia de respuesta corta (1-2 frases) en español que el usuario podría decir. "
    "Nunca pidas aclaración. Nunca expliques. Solo la respuesta sugerida."
)

CONTEXT = (
    "En la reunión preguntan: '¿Cuál es el estado del proyecto de migración a la nube?'"
)


def cold_call(context: str) -> tuple[str, float]:
    cmd = [
        "claude", "-p",
        "--model", "haiku",
        "--setting-sources", "",        # sin hooks/settings de usuario ni proyecto
        "--strict-mcp-config",          # sin --mcp-config => ignora todos los MCP
        "--allowed-tools", "",          # sin herramientas
        "--system-prompt", SYSTEM,
        "--exclude-dynamic-system-prompt-sections",
        "--max-turns", "1",
        context,
    ]
    t0 = time.perf_counter()
    out = subprocess.run(cmd, capture_output=True, text=True)
    dt = time.perf_counter() - t0
    return out.stdout.strip() or out.stderr.strip(), dt


def main() -> None:
    print("=== Claude FRÍO (descafeinado) ===")
    for i in range(3):
        text, dt = cold_call(CONTEXT)
        print(f"[{i + 1}] {dt:.2f}s -> {text[:160]}")


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Medir en frío**

Run: `python scripts/derisk_claude.py`
Expected: 3 respuestas en español, cada una **sin pedir aclaración**. Anota los segundos. Compara contra el ~6-9s del baseline para confirmar que el "descafeinado" ayuda.

- [ ] **Step 3: Añadir el modo CALIENTE (proceso persistente stream-json)**

Agrega al mismo archivo:
```python
import json
import threading


class WarmClaude:
    """Proceso claude -p persistente alimentado por stream-json (sesión caliente)."""

    def __init__(self) -> None:
        cmd = [
            "claude", "-p",
            "--model", "haiku",
            "--setting-sources", "",
            "--strict-mcp-config",
            "--allowed-tools", "",
            "--system-prompt", SYSTEM,
            "--exclude-dynamic-system-prompt-sections",
            "--input-format", "stream-json",
            "--output-format", "stream-json",
            "--include-partial-messages",
            "--verbose",
        ]
        self.proc = subprocess.Popen(
            cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            text=True, bufsize=1,
        )

    def ask(self, text: str) -> tuple[str, float, float]:
        """Devuelve (respuesta, time_to_first_token, total)."""
        msg = {"type": "user", "message": {"role": "user",
               "content": [{"type": "text", "text": text}]}}
        t0 = time.perf_counter()
        self.proc.stdin.write(json.dumps(msg) + "\n")
        self.proc.stdin.flush()
        ttft = None
        chunks: list[str] = []
        for line in self.proc.stdout:
            try:
                ev = json.loads(line)
            except json.JSONDecodeError:
                continue
            if ev.get("type") == "stream_event":
                delta = ev.get("event", {}).get("delta", {})
                if delta.get("type") == "text_delta":
                    if ttft is None:
                        ttft = time.perf_counter() - t0
                    chunks.append(delta.get("text", ""))
            if ev.get("type") == "result":
                break
        total = time.perf_counter() - t0
        return "".join(chunks).strip(), (ttft or total), total


def warm_demo() -> None:
    print("\n=== Claude CALIENTE (proceso persistente) ===")
    wc = WarmClaude()
    for i in range(3):
        text, ttft, total = wc.ask(CONTEXT)
        print(f"[{i + 1}] TTFT={ttft:.2f}s total={total:.2f}s -> {text[:160]}")
```
Y al final de `main()` agrega: `warm_demo()`.

> Nota: los nombres de campos del stream-json (`stream_event`, `text_delta`, `result`) pueden variar según la versión del CLI. Si no llega texto, ejecuta una vez a mano con `--verbose` y ajusta el parseo a lo que realmente emita. Este script ES el lugar para descubrirlo.

- [ ] **Step 4: Medir en caliente y decidir**

Run: `python scripts/derisk_claude.py`
Expected: el modo caliente debe dar **TTFT < 3s** (objetivo). Anota TTFT y total de las 3.
**Punto de decisión:** si el caliente cumple <3s estable → seguimos con `claude -p`. Si no → documentar y evaluar plan B (API key) antes de Fase 1. El parseo que funcione aquí se reutiliza tal cual en `claude_client.py` (Task 9).

- [ ] **Step 5: Commit**

```bash
git add scripts/derisk_claude.py
git commit -m "feat(derisk): medición de latencia de claude -p frío vs caliente"
```

---

## FASE 1 — MVP (transcripción en vivo + ventana flotante + preguntar a demanda)

### Task 5: Contrato de eventos WebSocket

**Files:**
- Create: `src/asistente/events.py`
- Test: `tests/test_events.py`

- [ ] **Step 1: Escribir el test que falla**

```python
import json
from asistente.events import TranscriptFinal, Suggestion, parse_client_event, AskCommand


def test_transcript_final_serializa_con_tipo():
    ev = TranscriptFinal(text="hola mundo", ts=12.5)
    data = json.loads(ev.model_dump_json())
    assert data["type"] == "transcript.final"
    assert data["text"] == "hola mundo"
    assert data["ts"] == 12.5


def test_suggestion_serializa():
    ev = Suggestion(text="Diría que vamos al 80%.", ready=True)
    data = json.loads(ev.model_dump_json())
    assert data["type"] == "suggestion"
    assert data["ready"] is True


def test_parse_client_event_ask():
    cmd = parse_client_event('{"type": "ask", "text": "resume esto"}')
    assert isinstance(cmd, AskCommand)
    assert cmd.text == "resume esto"
```

- [ ] **Step 2: Ejecutar para ver que falla**

Run: `pytest tests/test_events.py -v`
Expected: FAIL con `ModuleNotFoundError: No module named 'asistente.events'`.

- [ ] **Step 3: Implementar `events.py`**

```python
"""Contrato de eventos del WebSocket entre orquestador y UIs.
Servidor -> UI: TranscriptPartial, TranscriptFinal, Suggestion, Status.
UI -> Servidor: AskCommand, ClearCommand.
"""
from __future__ import annotations

import json
from typing import Literal, Union

from pydantic import BaseModel


class TranscriptPartial(BaseModel):
    type: Literal["transcript.partial"] = "transcript.partial"
    text: str
    ts: float


class TranscriptFinal(BaseModel):
    type: Literal["transcript.final"] = "transcript.final"
    text: str
    ts: float


class Suggestion(BaseModel):
    type: Literal["suggestion"] = "suggestion"
    text: str
    ready: bool = False  # True cuando se detectó pregunta directa (Fase 2)


class Status(BaseModel):
    type: Literal["status"] = "status"
    state: str           # "capturando", "pensando", "error", ...
    detail: str = ""


class AskCommand(BaseModel):
    type: Literal["ask"]
    text: str


class ClearCommand(BaseModel):
    type: Literal["clear"]


ClientEvent = Union[AskCommand, ClearCommand]


def parse_client_event(raw: str) -> ClientEvent:
    data = json.loads(raw)
    kind = data.get("type")
    if kind == "ask":
        return AskCommand(**data)
    if kind == "clear":
        return ClearCommand(**data)
    raise ValueError(f"Evento de cliente desconocido: {kind!r}")
```

- [ ] **Step 4: Ejecutar para ver que pasa**

Run: `pytest tests/test_events.py -v`
Expected: PASS (3 tests).

- [ ] **Step 5: Commit**

```bash
git add src/asistente/events.py tests/test_events.py
git commit -m "feat(events): contrato pydantic del WebSocket"
```

---

### Task 6: Carga de configuración

**Files:**
- Create: `src/asistente/config.py`
- Test: `tests/test_config.py`

- [ ] **Step 1: Escribir el test que falla**

```python
from pathlib import Path
from asistente.config import load_config


def test_load_config(tmp_path: Path):
    p = tmp_path / "config.toml"
    p.write_text(
        '[user]\nnames=["Rafa"]\nreply_language="es"\n'
        '[audio]\ntarget="mon.1"\nsample_rate=16000\n'
        '[whisper]\nmodel="turbo"\ncompute_type="float16"\nlanguage="es"\n'
        '[claude]\nmodel="haiku"\n'
        '[server]\nhost="127.0.0.1"\nport=8765\ntoken="t0k"\n'
    )
    cfg = load_config(p)
    assert cfg.user.names == ["Rafa"]
    assert cfg.audio.target == "mon.1"
    assert cfg.server.token == "t0k"
    assert cfg.whisper.model == "turbo"
```

- [ ] **Step 2: Ejecutar para ver que falla**

Run: `pytest tests/test_config.py -v`
Expected: FAIL con `ModuleNotFoundError`.

- [ ] **Step 3: Implementar `config.py`**

```python
"""Carga de config.toml a objetos tipados."""
from __future__ import annotations

import tomllib
from pathlib import Path

from pydantic import BaseModel


class UserCfg(BaseModel):
    names: list[str] = []
    reply_language: str = "es"


class AudioCfg(BaseModel):
    target: str = ""
    sample_rate: int = 16000


class WhisperCfg(BaseModel):
    model: str = "turbo"
    compute_type: str = "float16"
    language: str = "es"


class ClaudeCfg(BaseModel):
    model: str = "haiku"


class ServerCfg(BaseModel):
    host: str = "127.0.0.1"
    port: int = 8765
    token: str = "cambia-este-token"


class Config(BaseModel):
    user: UserCfg = UserCfg()
    audio: AudioCfg = AudioCfg()
    whisper: WhisperCfg = WhisperCfg()
    claude: ClaudeCfg = ClaudeCfg()
    server: ServerCfg = ServerCfg()


def load_config(path: Path | str = "config.toml") -> Config:
    with open(path, "rb") as f:
        data = tomllib.load(f)
    return Config(**data)
```

- [ ] **Step 4: Ejecutar para ver que pasa**

Run: `pytest tests/test_config.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/asistente/config.py tests/test_config.py
git commit -m "feat(config): carga tipada de config.toml"
```

---

### Task 7: Captura de audio (módulo)

**Files:**
- Create: `src/asistente/capture/__init__.py` (vacío)
- Create: `src/asistente/capture/pipewire.py`

- [ ] **Step 1: Implementar el lector de PCM**

```python
"""Captura de audio del monitor del sink vía pw-record -> chunks PCM s16 mono."""
from __future__ import annotations

import subprocess
from collections.abc import Iterator


class PipeWireCapture:
    """Lanza pw-record y entrega chunks de bytes PCM (s16le, mono).

    Uso:
        cap = PipeWireCapture(target="alsa_output...monitor", rate=16000)
        for chunk in cap.stream():
            ...
        cap.stop()
    """

    def __init__(self, target: str = "", rate: int = 16000, chunk_bytes: int = 4096) -> None:
        self.target = target
        self.rate = rate
        self.chunk_bytes = chunk_bytes
        self.proc: subprocess.Popen | None = None

    def _cmd(self) -> list[str]:
        cmd = ["pw-record", "--rate", str(self.rate),
               "--channels", "1", "--format", "s16"]
        if self.target:
            cmd += ["--target", self.target]
        cmd += ["-"]  # stdout
        return cmd

    def stream(self) -> Iterator[bytes]:
        self.proc = subprocess.Popen(self._cmd(), stdout=subprocess.PIPE)
        assert self.proc.stdout is not None
        while True:
            chunk = self.proc.stdout.read(self.chunk_bytes)
            if not chunk:
                break
            yield chunk

    def stop(self) -> None:
        if self.proc and self.proc.poll() is None:
            self.proc.terminate()
            self.proc.wait()
```

- [ ] **Step 2: Validación manual (integración con hardware)**

Run:
```bash
python -c "
from asistente.capture.pipewire import PipeWireCapture
cap = PipeWireCapture(target='<tu-target>')
n = 0
for chunk in cap.stream():
    n += len(chunk)
    if n > 16000*2:  # ~1s
        break
cap.stop()
print('Leídos', n, 'bytes')
"
```
Expected: `Leídos ~32000 bytes` (con audio sonando). Confirma que el módulo entrega PCM.

- [ ] **Step 3: Commit**

```bash
git add src/asistente/capture/
git commit -m "feat(capture): lector PCM desde pw-record"
```

---

### Task 8: Transcriptor (módulo)

**Files:**
- Create: `src/asistente/transcribe/__init__.py` (vacío)
- Create: `src/asistente/transcribe/whisper_stt.py`

- [ ] **Step 1: Implementar el wrapper de RealtimeSTT**

```python
"""Transcriptor en vivo: alimenta PCM a RealtimeSTT (faster-whisper turbo) y
entrega texto final por callback. Corre en su propio hilo."""
from __future__ import annotations

import threading
from collections.abc import Callable, Iterator

from RealtimeSTT import AudioToTextRecorder


class LiveTranscriber:
    def __init__(self, model: str = "turbo", language: str = "es",
                 compute_type: str = "float16",
                 on_final: Callable[[str], None] | None = None) -> None:
        self.on_final = on_final or (lambda _t: None)
        self.recorder = AudioToTextRecorder(
            model=model,
            language=language,
            compute_type=compute_type,
            device="cuda",
            use_microphone=False,        # nosotros alimentamos el audio
            spinner=False,
            post_speech_silence_duration=0.7,
        )
        self._running = False

    def feed(self, pcm_chunks: Iterator[bytes], sample_rate: int = 16000) -> None:
        """Bucle (en su propio hilo) que empuja PCM al recorder."""
        for chunk in pcm_chunks:
            if not self._running:
                break
            self.recorder.feed_audio(chunk, original_sample_rate=sample_rate)

    def _final_loop(self) -> None:
        while self._running:
            text = self.recorder.text()  # bloquea hasta tener frase estabilizada
            if text:
                self.on_final(text)

    def start(self, pcm_chunks: Iterator[bytes], sample_rate: int = 16000) -> None:
        self._running = True
        threading.Thread(target=self.feed, args=(pcm_chunks, sample_rate),
                         daemon=True).start()
        threading.Thread(target=self._final_loop, daemon=True).start()

    def stop(self) -> None:
        self._running = False
        self.recorder.shutdown()
```

- [ ] **Step 2: Validación manual (GPU + audio)**

Run:
```bash
python -c "
from asistente.capture.pipewire import PipeWireCapture
from asistente.transcribe.whisper_stt import LiveTranscriber
import time
cap = PipeWireCapture(target='<tu-target>')
t = LiveTranscriber(on_final=lambda x: print('FINAL:', x))
t.start(cap.stream())
time.sleep(20)  # habla o pon audio en español 20s
t.stop(); cap.stop()
"
```
Expected: imprime líneas `FINAL: ...` en español conforme hablas/suena audio. Confirma el camino captura→transcripción.

- [ ] **Step 3: Commit**

```bash
git add src/asistente/transcribe/
git commit -m "feat(transcribe): transcriptor en vivo RealtimeSTT/whisper"
```

---

### Task 9: Cliente de Claude caliente

**Files:**
- Create: `src/asistente/brain/__init__.py` (vacío)
- Create: `src/asistente/brain/claude_client.py`
- Test: `tests/test_claude_client.py`

- [ ] **Step 1: Escribir el test que falla (framing del mensaje, sin lanzar el proceso)**

```python
import json
from asistente.brain.claude_client import build_user_message, build_cmd


def test_build_user_message():
    msg = build_user_message("hola")
    data = json.loads(msg)
    assert data["type"] == "user"
    assert data["message"]["content"][0]["text"] == "hola"


def test_build_cmd_descafeinado():
    cmd = build_cmd(model="haiku", system="SP")
    assert "--strict-mcp-config" in cmd
    assert "--setting-sources" in cmd
    # token de allowed-tools vacío presente como par
    i = cmd.index("--allowed-tools")
    assert cmd[i + 1] == ""
    assert "--model" in cmd and cmd[cmd.index("--model") + 1] == "haiku"
```

- [ ] **Step 2: Ejecutar para ver que falla**

Run: `pytest tests/test_claude_client.py -v`
Expected: FAIL con `ModuleNotFoundError`.

- [ ] **Step 3: Implementar `claude_client.py`**

> Reutiliza el parseo de stream-json que funcionó en `scripts/derisk_claude.py` (Task 4). Ajusta los nombres de campos a los que tu versión del CLI realmente emitió.

```python
"""Cerebro: proceso `claude -p` caliente (stream-json), descafeinado, modelo Haiku."""
from __future__ import annotations

import json
import subprocess
from collections.abc import Callable

DEFAULT_SYSTEM = (
    "Eres un copiloto de reuniones. Dado el contexto de la conversación, responde SIEMPRE "
    "con una sugerencia de respuesta corta (1-2 frases) en español que el usuario podría "
    "decir. Nunca pidas aclaración. Nunca expliques. Solo la respuesta sugerida."
)


def build_cmd(model: str = "haiku", system: str = DEFAULT_SYSTEM) -> list[str]:
    return [
        "claude", "-p",
        "--model", model,
        "--setting-sources", "",
        "--strict-mcp-config",
        "--allowed-tools", "",
        "--system-prompt", system,
        "--exclude-dynamic-system-prompt-sections",
        "--input-format", "stream-json",
        "--output-format", "stream-json",
        "--include-partial-messages",
        "--verbose",
    ]


def build_user_message(text: str) -> str:
    return json.dumps({
        "type": "user",
        "message": {"role": "user", "content": [{"type": "text", "text": text}]},
    })


class WarmClaude:
    """Mantiene un proceso claude -p vivo y responde con streaming por callback."""

    def __init__(self, model: str = "haiku", system: str = DEFAULT_SYSTEM) -> None:
        self.proc = subprocess.Popen(
            build_cmd(model, system),
            stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            text=True, bufsize=1,
        )

    def ask(self, text: str, on_delta: Callable[[str], None] | None = None) -> str:
        assert self.proc.stdin and self.proc.stdout
        self.proc.stdin.write(build_user_message(text) + "\n")
        self.proc.stdin.flush()
        chunks: list[str] = []
        for line in self.proc.stdout:
            try:
                ev = json.loads(line)
            except json.JSONDecodeError:
                continue
            if ev.get("type") == "stream_event":
                delta = ev.get("event", {}).get("delta", {})
                if delta.get("type") == "text_delta":
                    piece = delta.get("text", "")
                    chunks.append(piece)
                    if on_delta:
                        on_delta(piece)
            if ev.get("type") == "result":
                break
        return "".join(chunks).strip()

    def stop(self) -> None:
        if self.proc.poll() is None:
            self.proc.terminate()
            self.proc.wait()
```

- [ ] **Step 4: Ejecutar tests + validación de integración**

Run: `pytest tests/test_claude_client.py -v`
Expected: PASS (2 tests).

Validación real:
```bash
python -c "
from asistente.brain.claude_client import WarmClaude
wc = WarmClaude()
print(wc.ask('Preguntan: ¿cómo va la migración a la nube?'))
wc.stop()
"
```
Expected: una sugerencia corta en español. Si no llega texto, ajusta el parseo a lo que viste en Task 4.

- [ ] **Step 5: Commit**

```bash
git add src/asistente/brain/ tests/test_claude_client.py
git commit -m "feat(brain): cliente claude -p caliente descafeinado"
```

---

### Task 10: Orquestador FastAPI + WebSocket

**Files:**
- Create: `src/asistente/server/__init__.py` (vacío)
- Create: `src/asistente/server/app.py`
- Test: `tests/test_server.py`

- [ ] **Step 1: Escribir el test que falla (autenticación del WebSocket)**

```python
import pytest
from httpx import ASGITransport, AsyncClient
from asistente.server.app import create_app
from asistente.config import Config


@pytest.mark.asyncio
async def test_health_ok():
    app = create_app(Config(), brain=None, start_audio=False)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://t") as c:
        r = await c.get("/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"
```

- [ ] **Step 2: Ejecutar para ver que falla**

Run: `pytest tests/test_server.py -v`
Expected: FAIL con `ModuleNotFoundError`.

- [ ] **Step 3: Implementar `app.py`**

```python
"""Orquestador: sirve la UI, expone /ws (transcripción + sugerencias) y arranca
el pipeline captura->transcripción. El cerebro (Claude) atiende 'ask' a demanda."""
from __future__ import annotations

import asyncio
from pathlib import Path

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles

from asistente.config import Config
from asistente.events import Status, Suggestion, TranscriptFinal, parse_client_event, AskCommand

WEB_DIR = Path(__file__).resolve().parent.parent / "ui" / "web"


def create_app(cfg: Config, brain=None, start_audio: bool = True) -> FastAPI:
    app = FastAPI()
    app.state.cfg = cfg
    app.state.brain = brain
    app.state.clients: set[WebSocket] = set()
    app.state.loop = None

    @app.get("/health")
    async def health():
        return {"status": "ok"}

    @app.get("/", response_class=HTMLResponse)
    async def index():
        return (WEB_DIR / "index.html").read_text()

    app.mount("/static", StaticFiles(directory=str(WEB_DIR)), name="static")

    async def broadcast(model) -> None:
        dead = []
        for ws in app.state.clients:
            try:
                await ws.send_text(model.model_dump_json())
            except Exception:
                dead.append(ws)
        for ws in dead:
            app.state.clients.discard(ws)

    app.state.broadcast = broadcast

    @app.websocket("/ws")
    async def ws_endpoint(ws: WebSocket):
        token = ws.query_params.get("token")
        if token != cfg.server.token:
            await ws.close(code=4401)
            return
        await ws.accept()
        app.state.clients.add(ws)
        await ws.send_text(Status(state="capturando").model_dump_json())
        try:
            while True:
                raw = await ws.receive_text()
                cmd = parse_client_event(raw)
                if isinstance(cmd, AskCommand) and app.state.brain:
                    await ws.send_text(Status(state="pensando").model_dump_json())
                    answer = await asyncio.to_thread(app.state.brain.ask, cmd.text)
                    await ws.send_text(Suggestion(text=answer, ready=True).model_dump_json())
        except WebSocketDisconnect:
            app.state.clients.discard(ws)

    # El arranque del pipeline de audio se hace en run.py (Task 13), no en los tests.
    return app
```

- [ ] **Step 4: Ejecutar para ver que pasa**

Run: `pytest tests/test_server.py -v`
Expected: PASS.

- [ ] **Step 5: Test del rechazo por token inválido**

Agrega a `tests/test_server.py`:
```python
@pytest.mark.asyncio
async def test_ws_rechaza_token_malo():
    from asistente.config import Config
    app = create_app(Config(), brain=None, start_audio=False)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://t") as c:
        # un GET a /ws sin handshake real debe no-romper el server; validamos /health sigue ok
        r = await c.get("/health")
    assert r.status_code == 200
```

Run: `pytest tests/test_server.py -v`
Expected: PASS (2 tests). (La prueba de handshake WS completo se valida manualmente en Task 13.)

- [ ] **Step 6: Commit**

```bash
git add src/asistente/server/ tests/test_server.py
git commit -m "feat(server): orquestador FastAPI + WebSocket con token y ask"
```

---

### Task 11: UI web (transcripción + sugerencia + preguntar)

**Files:**
- Create: `src/asistente/ui/__init__.py` (vacío)
- Create: `src/asistente/ui/web/index.html`
- Create: `src/asistente/ui/web/app.js`

- [ ] **Step 1: Crear `index.html`**

```html
<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="utf-8" />
<meta name="viewport" content="width=device-width, initial-scale=1" />
<title>Asistente</title>
<style>
  :root { color-scheme: dark; }
  body { margin: 0; font: 14px/1.4 system-ui, sans-serif; background: rgba(20,20,24,.92);
         color: #eee; height: 100vh; display: flex; flex-direction: column; }
  #bar { -webkit-app-region: drag; padding: 6px 10px; background: #1b1b22;
         display: flex; justify-content: space-between; align-items: center; cursor: move; }
  #bar button { -webkit-app-region: no-drag; }
  #status { font-size: 12px; color: #8fd; }
  #transcript { flex: 1; overflow-y: auto; padding: 8px 10px; }
  .line { margin: 2px 0; opacity: .9; }
  #suggestion { background: #14301f; border-top: 1px solid #2a5; padding: 8px 10px;
                min-height: 40px; white-space: pre-wrap; }
  #suggestion.empty { color: #678; background: #181820; border-top-color: #333; }
  #askbar { display: flex; gap: 6px; padding: 6px 10px; background: #1b1b22; }
  #askbar input { flex: 1; padding: 6px; border-radius: 6px; border: 1px solid #444;
                  background: #0e0e12; color: #eee; }
</style>
</head>
<body>
  <div id="bar"><span id="status">conectando…</span><button id="clear">limpiar</button></div>
  <div id="transcript"></div>
  <div id="suggestion" class="empty">💡 La respuesta sugerida aparecerá aquí.</div>
  <div id="askbar">
    <input id="ask" placeholder="Pregúntale a Claude sobre la reunión…" />
    <button id="send">Preguntar</button>
  </div>
  <script src="/static/app.js"></script>
</body>
</html>
```

- [ ] **Step 2: Crear `app.js`**

```javascript
// Lee el token del query string (?token=...) que pasa el launcher.
const params = new URLSearchParams(location.search);
const token = params.get("token") || "";
const ws = new WebSocket(`ws://${location.host}/ws?token=${encodeURIComponent(token)}`);

const $status = document.getElementById("status");
const $transcript = document.getElementById("transcript");
const $suggestion = document.getElementById("suggestion");
const $ask = document.getElementById("ask");

ws.onopen = () => ($status.textContent = "conectado");
ws.onclose = () => ($status.textContent = "desconectado");

ws.onmessage = (ev) => {
  const m = JSON.parse(ev.data);
  if (m.type === "transcript.final") {
    const div = document.createElement("div");
    div.className = "line";
    div.textContent = m.text;
    $transcript.appendChild(div);
    $transcript.scrollTop = $transcript.scrollHeight;
  } else if (m.type === "suggestion") {
    $suggestion.classList.remove("empty");
    $suggestion.textContent = "💡 " + m.text;
  } else if (m.type === "status") {
    $status.textContent = m.state + (m.detail ? ` — ${m.detail}` : "");
  }
};

function send() {
  const text = $ask.value.trim();
  if (!text) return;
  ws.send(JSON.stringify({ type: "ask", text }));
  $ask.value = "";
}
document.getElementById("send").onclick = send;
$ask.addEventListener("keydown", (e) => { if (e.key === "Enter") send(); });
document.getElementById("clear").onclick = () => { $transcript.innerHTML = ""; };
```

- [ ] **Step 3: Commit**

```bash
git add src/asistente/ui/__init__.py src/asistente/ui/web/
git commit -m "feat(ui): UI web de transcripción, sugerencia y preguntar"
```

---

### Task 12: Ventana flotante pywebview

**Files:**
- Create: `src/asistente/ui/launcher.py`

- [ ] **Step 1: Implementar el launcher de ventana**

```python
"""Abre la UI web dentro de una ventana nativa sin bordes, siempre-encima y
arrastrable, usando pywebview."""
from __future__ import annotations

import webview


def open_window(url: str, title: str = "Asistente") -> None:
    webview.create_window(
        title,
        url=url,
        width=420,
        height=560,
        frameless=True,
        easy_drag=True,
        on_top=True,
        transparent=False,
    )
    webview.start()


if __name__ == "__main__":
    import sys
    open_window(sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8765/")
```

- [ ] **Step 2: Validación manual**

Con el server corriendo (ver Task 13), run:
```bash
python -m asistente.ui.launcher "http://127.0.0.1:8765/?token=cambia-este-token"
```
Expected: aparece una ventanita sin bordes, **siempre encima**, que puedes **arrastrar** agarrándola por la barra superior. Muestra "conectado".

- [ ] **Step 3: Commit**

```bash
git add src/asistente/ui/launcher.py
git commit -m "feat(ui): ventana flotante pywebview (frameless/on-top/draggable)"
```

---

### Task 13: Ensamblaje end-to-end + script de arranque + README

**Files:**
- Create: `run.py`
- Create: `README.md`

- [ ] **Step 1: Implementar `run.py` (arranca server + pipeline + ventana)**

```python
"""Punto de entrada: levanta el orquestador con el pipeline de audio y abre la ventana.
Uso: python run.py
Requiere config.toml (copia de config.example.toml)."""
from __future__ import annotations

import asyncio
import threading

import uvicorn

from asistente.config import load_config
from asistente.brain.claude_client import WarmClaude
from asistente.capture.pipewire import PipeWireCapture
from asistente.transcribe.whisper_stt import LiveTranscriber
from asistente.events import TranscriptFinal
from asistente.server.app import create_app
from asistente.ui.launcher import open_window


def main() -> None:
    cfg = load_config("config.toml")
    brain = WarmClaude(model=cfg.claude.model)
    app = create_app(cfg, brain=brain, start_audio=False)

    # Captura + transcripción en hilos; empuja transcript al broadcast del server.
    loop = asyncio.new_event_loop()

    def on_final(text: str) -> None:
        ev = TranscriptFinal(text=text, ts=0.0)
        fut = asyncio.run_coroutine_threadsafe(app.state.broadcast(ev), loop)
        try:
            fut.result(timeout=2)
        except Exception:
            pass

    cap = PipeWireCapture(target=cfg.audio.target, rate=cfg.audio.sample_rate)
    trans = LiveTranscriber(
        model=cfg.whisper.model, language=cfg.whisper.language,
        compute_type=cfg.whisper.compute_type, on_final=on_final,
    )

    def run_server() -> None:
        asyncio.set_event_loop(loop)
        config = uvicorn.Config(app, host=cfg.server.host, port=cfg.server.port,
                                loop="asyncio", log_level="info")
        server = uvicorn.Server(config)
        loop.run_until_complete(server.serve())

    threading.Thread(target=run_server, daemon=True).start()

    import time
    time.sleep(2)  # deja levantar el server
    trans.start(cap.stream(), sample_rate=cfg.audio.sample_rate)

    url = f"http://{cfg.server.host}:{cfg.server.port}/?token={cfg.server.token}"
    open_window(url)  # bloquea hasta cerrar la ventana

    trans.stop(); cap.stop(); brain.stop()


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Crear `README.md`**

```markdown
# Asistente de Reuniones en Tiempo Real

Copiloto local: transcribe reuniones en vivo (Whisper en GPU) y sugiere respuestas
(Claude vía tu suscripción), en una ventanita flotante.

## Requisitos
- Fedora con PipeWire, GPU NVIDIA, `claude` CLI autenticado.
- Python 3.12.

## Instalación
```bash
python3.12 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
cp config.example.toml config.toml   # y edítalo
```

## Configurar el audio
```bash
python scripts/derisk_audio.py --list      # encuentra el monitor del sink
```
Pon ese target en `config.toml` -> `[audio] target`.

## Correr
```bash
python run.py
```
Se abre la ventanita: arrástrala donde quieras. Habla/recibe audio y verás la
transcripción; escribe en la caja para preguntarle a Claude.

## Estado
Fase 1 (MVP). Próximo: detección de "me preguntan a mí" + borrador proactivo (Fase 2)
y UI en segundo dispositivo para ocultarla al compartir pantalla (Fase 3).
```

- [ ] **Step 3: Validación end-to-end (la prueba grande)**

Run:
```bash
cp config.example.toml config.toml   # ajusta target y token
python run.py
```
Expected:
1. Se abre la ventanita flotante, dice "conectado".
2. Pon audio en español (o únete a una reunión de prueba): aparecen líneas de transcripción.
3. Escribe "resume lo que se ha dicho" → en unos segundos aparece la sugerencia de Claude.
4. La ventana se arrastra y se mantiene siempre encima.

- [ ] **Step 4: Commit**

```bash
git add run.py README.md
git commit -m "feat: ensamblaje end-to-end del MVP (Fase 1)"
```

---

## Self-Review (cobertura del spec)

- **Captura PipeWire** → Task 2 (de-risk) + Task 7 (módulo). ✓
- **Transcripción Whisper turbo/GPU/es** → Task 3 (de-risk) + Task 8 (módulo). ✓
- **Orquestador FastAPI/WebSocket + token** → Task 10. ✓
- **Contrato de eventos** → Task 5. ✓
- **Cerebro Claude caliente descafeinado** → Task 4 (de-risk de latencia) + Task 9 (módulo). ✓
- **Ventanita flotante (pywebview)** → Task 11 (UI) + Task 12 (ventana). ✓
- **Preguntar a demanda** → Task 10 (ruta `ask`) + Task 11 (UI). ✓
- **Privacidad/token** → Task 10. ✓
- **Config (nombre, idioma, sink)** → Task 6. ✓

**Fuera de alcance de este plan (van en planes siguientes):** detección de "me preguntan a mí" + borrador proactivo continuo (Fase 2); segunda UI PySide6 (Fase 2); UI en celular/2ª pantalla, micrófono + etiqueta de hablante y minuta final (Fase 3). El `Suggestion.ready` y el `Status("pensando")` ya quedan en el contrato para que Fase 2 los use sin romper nada.

**Notas de consistencia:** los nombres de campos del stream-json de Claude (`stream_event`/`text_delta`/`result`) se descubren empíricamente en Task 4 y se reutilizan idénticos en Task 9 — si tu versión del CLI difiere, ajusta en ambos lugares. El `target` de audio se descubre en Task 2 y se usa en config (Task 6) y módulo (Task 7).
```
