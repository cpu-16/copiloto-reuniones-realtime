"""Transcriptor en vivo: alimenta PCM a RealtimeSTT (faster-whisper) y entrega
texto en tiempo real. Corre en sus propios hilos.

Emite DOS señales:
- on_partial: texto parcial continuo MIENTRAS se habla (modelo realtime ligero).
- on_final:   frase estabilizada al detectar una pausa (modelo principal, más preciso).

Los parciales son imprescindibles para audio de reunión continuo: casi nunca hay
0.7s de silencio limpio que dispare un final, así que sin parciales no saldría nada.
"""
from __future__ import annotations

import threading
from collections.abc import Callable, Iterator

from RealtimeSTT import AudioToTextRecorder


class LiveTranscriber:
    def __init__(self, model: str = "turbo", language: str = "es",
                 compute_type: str = "float16",
                 realtime_model: str = "small",
                 realtime_pause: float = 0.2,
                 enable_realtime: bool = True,
                 device: str = "cuda",
                 on_final: Callable[[str], None] | None = None,
                 on_partial: Callable[[str], None] | None = None) -> None:
        self.on_final = on_final or (lambda _t: None)
        self.on_partial = on_partial or (lambda _t: None)
        # "" o "auto" => autodetección por Whisper (reuniones bilingües es/en).
        lang = "" if language in ("", "auto", None) else language
        # float16 no existe en CPU (CTranslate2): se fuerza int8 si device="cpu".
        if device == "cpu" and compute_type in ("float16", "fp16"):
            compute_type = "int8"
        self.recorder = AudioToTextRecorder(
            model=model,
            language=lang,
            compute_type=compute_type,
            device=device,
            use_microphone=False,        # nosotros alimentamos el audio
            spinner=False,
            post_speech_silence_duration=0.7,
            # Parciales en vivo: más pesados para la GPU (re-transcribe cada
            # `realtime_pause` s). Subir la pausa o usar un modelo más chico baja
            # el consumo; enable_realtime=False lo apaga (solo finales = mínima GPU).
            enable_realtime_transcription=enable_realtime,
            realtime_model_type=realtime_model,
            realtime_processing_pause=realtime_pause,
            on_realtime_transcription_stabilized=self._on_realtime,
        )
        self._running = False

    def _on_realtime(self, text: str) -> None:
        if text:
            self.on_partial(text)

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
