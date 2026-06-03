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
