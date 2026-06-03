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
