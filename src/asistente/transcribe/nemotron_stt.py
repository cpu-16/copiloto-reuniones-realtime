"""Transcriptor en vivo con NVIDIA Nemotron 3.5 ASR streaming 0.6B (NeMo, cache-aware).

RNN-T FastConformer cache-aware: streaming nativo de baja latencia (a diferencia de
Parakeet, que re-transcribe el buffer con VAD-RMS). El audio fluye continuo y el modelo
emite la transcripción ACUMULADA por paso; la segmentamos en finales (endpoint.py) y
emitimos el resto como parcial.

Mismo interfaz que los demás transcriptores: start(pcm_chunks, sr), stop(),
callbacks on_partial / on_final. Requiere el venv `.venv-nemotron` (NeMo 26.06+).

NOTA: el dimensionamiento exacto de la ventana (chunk/shift/pre-encode) y la selección
de idioma se VALIDAN con scripts/derisk_nemotron.py sobre la GPU real antes de confiar en
producción. El loop sigue el API real de NeMo (conformer_stream_step + preprocessor),
verificado contra el NeMo instalado.
"""
from __future__ import annotations

import copy
import threading
import time
from collections.abc import Callable, Iterator

import numpy as np

from asistente.transcribe.correct import correct_terms
from asistente.transcribe.endpoint import segment_finals


def _select(value, first: bool):
    """streaming_cfg expone algunos parámetros como [primer_paso, resto] o como escalar."""
    if isinstance(value, (list, tuple)):
        return value[0] if first else value[1]
    return value


class NemotronTranscriber:
    def __init__(self, model_name: str = "nvidia/nemotron-3.5-asr-streaming-0.6b",
                 att_context_size: list[int] | None = None,
                 target_lang: str = "es",
                 glossary: list[str] | None = None,
                 correct_enabled: bool = True,
                 pause_finalize_s: float = 0.8,
                 on_final: Callable[[str], None] | None = None,
                 on_partial: Callable[[str], None] | None = None) -> None:
        self.on_final = on_final or (lambda _t: None)
        self.on_partial = on_partial or (lambda _t: None)
        self.att_context_size = att_context_size or [56, 13]   # 1120ms: mejor precisión
        self.target_lang = target_lang
        self.glossary = glossary or []
        self.correct_enabled = correct_enabled
        self.pause_finalize_s = pause_finalize_s
        self.sample_rate = 16000

        import torch
        from omegaconf import OmegaConf
        from nemo.collections.asr.models import ASRModel
        self._torch = torch

        self._device = torch.device("cuda:0")
        # Carga OOM-safe: CPU -> fp16 -> cuda (evita el pico fp32 en GPU).
        model = ASRModel.from_pretrained(model_name, map_location="cpu")
        self.model = model.half().to(self._device).eval()
        self._maybe_set_language()
        # set_default_att_context_size invoca setup_streaming_params() internamente.
        self.model.encoder.set_default_att_context_size(self.att_context_size)
        self._scfg = self.model.encoder.streaming_cfg

        # Preprocessor con normalización desactivada (la hacemos por chunk con
        # normalize_batch, como en streaming_utils de NeMo).
        pre_cfg = copy.deepcopy(self.model._cfg.preprocessor)
        self._normalization = pre_cfg.normalize
        OmegaConf.set_struct(pre_cfg, False)
        pre_cfg.dither = 0.0
        pre_cfg.pad_to = 0
        pre_cfg.normalize = "None"
        self._preprocessor = self.model.from_config_dict(pre_cfg).to(self._device).eval()

        window_stride = float(self.model.cfg.preprocessor.window_stride)
        self._hop = round(self.sample_rate * window_stride)   # muestras por frame (~160)

        self._pcm = bytearray()
        self._lock = threading.Lock()
        self._running = False

    def _maybe_set_language(self) -> None:
        """Best-effort: fija el idioma de transcripción si el modelo lo soporta. El API
        exacto se confirma en el de-risk; no es fatal si no aplica."""
        for attr in ("set_source_lang", "set_target_lang", "set_prompt_lang"):
            fn = getattr(self.model, attr, None)
            if callable(fn):
                try:
                    fn(self.target_lang)
                    return
                except Exception:  # noqa: BLE001
                    pass

    # ---- alimentación de audio ----
    def feed(self, pcm_chunks: Iterator[bytes], sample_rate: int = 16000) -> None:
        self.sample_rate = sample_rate
        for chunk in pcm_chunks:
            if not self._running:
                break
            with self._lock:
                self._pcm.extend(chunk)

    def _read_samples(self, n: int) -> np.ndarray | None:
        """Bloquea hasta tener n muestras (n*2 bytes) o hasta que se detenga."""
        need = n * 2
        while self._running:
            with self._lock:
                if len(self._pcm) >= need:
                    raw = bytes(self._pcm[:need])
                    del self._pcm[:need]
                    return np.frombuffer(raw, dtype="<i2").astype(np.float32) / 32768.0
            time.sleep(0.01)
        return None

    # ---- loop de streaming ----
    def _worker(self) -> None:
        torch = self._torch
        from nemo.collections.asr.parts.preprocessing.features import normalize_batch

        cache_ch, cache_t, cache_len = self.model.encoder.get_initial_cache_state(
            batch_size=1, dtype=torch.float16, device=self._device, max_dim=0
        )
        previous_hypotheses = None
        pred_out_stream = None
        pcm_history = np.empty(0, dtype=np.float32)
        emitted = 0          # chars ya finalizados de la transcripción acumulada
        last_growth = time.monotonic()
        last_full = ""
        step = 0

        while self._running:
            first = step == 0
            chunk_frames = _select(self._scfg.chunk_size, first)
            shift_frames = _select(self._scfg.shift_size, first)
            pre_cache_frames = _select(self._scfg.pre_encode_cache_size, first)
            drop_extra = 0 if first else self._scfg.drop_extra_pre_encoded

            new_frames = chunk_frames if first else shift_frames
            new_pcm = self._read_samples(new_frames * self._hop)
            if new_pcm is None:
                break
            pcm_history = np.concatenate((pcm_history, new_pcm))

            wanted_frames = pre_cache_frames + chunk_frames
            wanted_samples = wanted_frames * self._hop
            window = pcm_history[-wanted_samples:]
            if window.size < wanted_samples:
                window = np.pad(window, (wanted_samples - window.size, 0))
            # No dejes crecer el historial sin límite.
            if pcm_history.size > wanted_samples * 4:
                pcm_history = pcm_history[-wanted_samples * 2:]

            input_signal = torch.from_numpy(window).unsqueeze(0).to(self._device)
            input_length = torch.tensor([window.size], device=self._device, dtype=torch.long)
            with torch.inference_mode(), torch.autocast("cuda", dtype=torch.float16):
                proc, _proc_len = self._preprocessor(input_signal=input_signal, length=input_length)
                proc = proc[..., -wanted_frames:]
                proc_len = torch.tensor([proc.shape[-1]], device=self._device, dtype=torch.long)
                proc, _, _ = normalize_batch(x=proc, seq_len=proc_len,
                                             normalize_type=self._normalization)
                (
                    pred_out_stream, _hyps, cache_ch, cache_t, cache_len, best_hyps,
                ) = self.model.conformer_stream_step(
                    processed_signal=proc,
                    processed_signal_length=proc_len,
                    cache_last_channel=cache_ch,
                    cache_last_time=cache_t,
                    cache_last_channel_len=cache_len,
                    keep_all_outputs=False,
                    previous_hypotheses=previous_hypotheses,
                    previous_pred_out=pred_out_stream,
                    drop_extra_pre_encoded=drop_extra,
                    return_transcription=True,
                )
            previous_hypotheses = best_hyps
            step += 1

            full = best_hyps[0].text if best_hyps else ""
            now = time.monotonic()
            if full != last_full:
                last_full = full
                last_growth = now

            finals, emitted, partial = segment_finals(full, emitted)
            for f in finals:
                self._emit_final(f)
            if partial:
                self.on_partial(partial)
            # Pausa: si el texto no crece y hay parcial pendiente, ciérralo como final.
            elif full[emitted:].strip() and (now - last_growth) >= self.pause_finalize_s:
                self._emit_final(full[emitted:].strip())
                emitted = len(full)

    def _emit_final(self, text: str) -> None:
        if self.correct_enabled and self.glossary:
            text = correct_terms(text, self.glossary)
        self.on_final(text)

    def start(self, pcm_chunks: Iterator[bytes], sample_rate: int = 16000) -> None:
        self._running = True
        threading.Thread(target=self.feed, args=(pcm_chunks, sample_rate),
                         daemon=True).start()
        threading.Thread(target=self._worker, daemon=True).start()

    def stop(self) -> None:
        self._running = False
