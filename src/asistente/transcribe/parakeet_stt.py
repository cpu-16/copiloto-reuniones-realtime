"""Transcriptor en vivo con NVIDIA Parakeet TDT 0.6B v3 (NeMo), fp16.

Mucho más liviano y rápido que Whisper para streaming (es un transductor):
re-transcribir el buffer en vivo cuesta ~0.04s y usa ~1.3GB de VRAM. VAD por energía
(RMS) en numpy puro, sin dependencias extra. Requiere el venv `.venv-parakeet` (NeMo).

Mismo interfaz que LiveTranscriber: on_partial (texto mientras se habla) + on_final
(frase al detectar una pausa). Parakeet v3 autodetecta idioma (es/en y 23 más).
"""
from __future__ import annotations

import threading
import time
from collections.abc import Callable, Iterator

import numpy as np


class ParakeetTranscriber:
    def __init__(self, model_name: str = "nvidia/parakeet-tdt-0.6b-v3",
                 realtime_pause: float = 0.4,
                 post_speech_silence: float = 0.7,
                 silence_rms: float = 350.0,      # umbral de silencio en escala int16
                 max_utterance_s: float = 20.0,   # corta y finaliza si una frase se alarga
                 on_final: Callable[[str], None] | None = None,
                 on_partial: Callable[[str], None] | None = None) -> None:
        self.on_final = on_final or (lambda _t: None)
        self.on_partial = on_partial or (lambda _t: None)
        self.realtime_pause = realtime_pause
        self.post_speech_silence = post_speech_silence
        self.silence_rms = silence_rms
        self.max_utterance_s = max_utterance_s
        self.sample_rate = 16000

        import nemo.collections.asr as nemo_asr
        # Cargar en CPU, pasar a fp16 y RECIÉN ahí mover a la GPU: así el pico de
        # VRAM al cargar es ~1.3GB (fp16) en vez de ~5GB (fp32), evitando OOM si la
        # GPU ya está ocupada por otra app.
        self.model = nemo_asr.models.ASRModel.from_pretrained(
            model_name, map_location="cpu"
        )
        self.model = self.model.half().to("cuda").eval()
        self._buf: list[np.ndarray] = []
        self._had_speech = False
        self._silence = 0.0
        self._lock = threading.Lock()
        self._running = False

    def _transcribe(self) -> str:
        with self._lock:
            if not self._buf:
                return ""
            audio = np.concatenate(self._buf)
        if audio.size < 1600:  # < 0.1s: nada útil
            return ""
        out = self.model.transcribe([audio], verbose=False)
        first = out[0]
        return (getattr(first, "text", first) or "").strip()

    def feed(self, pcm_chunks: Iterator[bytes], sample_rate: int = 16000) -> None:
        self.sample_rate = sample_rate
        for chunk in pcm_chunks:
            if not self._running:
                break
            a16 = np.frombuffer(chunk, dtype=np.int16)
            if a16.size == 0:
                continue
            rms = float(np.sqrt(np.mean(a16.astype(np.float32) ** 2)))
            dur = a16.size / sample_rate
            af = a16.astype(np.float32) / 32768.0
            with self._lock:
                self._buf.append(af)
                if rms >= self.silence_rms:
                    self._had_speech = True
                    self._silence = 0.0
                elif self._had_speech:
                    self._silence += dur

    def _buf_seconds(self) -> float:
        with self._lock:
            return sum(a.size for a in self._buf) / self.sample_rate

    def _finalize(self) -> None:
        text = self._transcribe()
        if text:
            self.on_final(text)
        with self._lock:
            self._buf.clear()
            self._had_speech = False
            self._silence = 0.0

    def _worker(self) -> None:
        last_partial = 0.0
        while self._running:
            time.sleep(0.1)
            now = time.monotonic()
            with self._lock:
                had, sil = self._had_speech, self._silence
            if not had:
                continue
            # Fin de frase por silencio, o por frase demasiado larga.
            if sil >= self.post_speech_silence or self._buf_seconds() >= self.max_utterance_s:
                self._finalize()
                last_partial = now
            elif now - last_partial >= self.realtime_pause:
                text = self._transcribe()
                if text:
                    self.on_partial(text)
                last_partial = now

    def start(self, pcm_chunks: Iterator[bytes], sample_rate: int = 16000) -> None:
        self._running = True
        threading.Thread(target=self.feed, args=(pcm_chunks, sample_rate),
                         daemon=True).start()
        threading.Thread(target=self._worker, daemon=True).start()

    def stop(self) -> None:
        self._running = False
