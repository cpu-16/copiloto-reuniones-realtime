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
