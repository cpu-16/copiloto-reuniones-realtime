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

_LEGACY_RMS = 350.0    # umbral histórico, usado como provisional/fallback


def calibrate_threshold(rms_values: list[float], factor: float = 2.5,
                        min_rms: float = 120.0) -> float:
    """Deriva el umbral de voz a partir del ruido de fondo medido.

    Usa el percentil 20 de los RMS observados como "piso de ruido" (robusto aunque
    haya algo de voz en la ventana de calibración: los huecos definen el piso) y lo
    escala por `factor`, con un mínimo de seguridad. Función pura → testeable sin GPU.
    """
    if not rms_values:
        return min_rms
    floor = float(np.percentile(np.asarray(rms_values, dtype=np.float32), 20))
    return max(floor * factor, min_rms)


class ParakeetTranscriber:
    def __init__(self, model_name: str = "nvidia/parakeet-tdt-0.6b-v3",
                 realtime_pause: float = 0.4,
                 post_speech_silence: float = 0.7,
                 silence_rms: float = 0.0,        # umbral de voz (int16); 0 = autocalibrar
                 auto_calibrate: bool = True,     # mide el piso de ruido al arrancar
                 calib_seconds: float = 1.5,      # ventana de calibración
                 max_utterance_s: float = 20.0,   # corta y finaliza si una frase se alarga
                 on_final: Callable[[str], None] | None = None,
                 on_partial: Callable[[str], None] | None = None) -> None:
        self.on_final = on_final or (lambda _t: None)
        self.on_partial = on_partial or (lambda _t: None)
        self.realtime_pause = realtime_pause
        self.post_speech_silence = post_speech_silence
        self.max_utterance_s = max_utterance_s
        self.sample_rate = 16000
        # Umbral de voz: manual (silence_rms>0) tiene prioridad; si no y auto_calibrate,
        # se mide al arrancar (provisional _LEGACY_RMS hasta calibrar); si no, fijo legacy.
        self.calib_seconds = calib_seconds
        if silence_rms and silence_rms > 0:
            self.silence_rms = float(silence_rms)
            self._calibrating = False
        elif auto_calibrate:
            self.silence_rms = _LEGACY_RMS
            self._calibrating = True
        else:
            self.silence_rms = _LEGACY_RMS
            self._calibrating = False
        self._calib_rms: list[float] = []
        self._calib_dur = 0.0

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
            # Autocalibración: en los primeros segundos medimos el ruido de fondo y
            # fijamos el umbral; no buffereamos ese audio (se descarta el arranque).
            if self._calibrating:
                self._calib_rms.append(rms)
                self._calib_dur += dur
                if self._calib_dur >= self.calib_seconds:
                    self.silence_rms = calibrate_threshold(self._calib_rms)
                    floor = float(np.percentile(self._calib_rms, 20)) if self._calib_rms else 0.0
                    print(f"  [parakeet] umbral autocalibrado: silence_rms="
                          f"{self.silence_rms:.0f} (piso≈{floor:.0f}, "
                          f"muestras={len(self._calib_rms)})")
                    self._calibrating = False
                continue
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
