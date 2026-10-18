"""Piper TTS: front end (phonemes, duration prediction, flow) on CPU onnxruntime, HiFi-GAN decoder
on the board NPU.

One voice .onnx is split into two graphs: <voice>.front.onnx (output length depends on input → CPU)
and <voice>.dec.onnx (Conv/ConvTranspose only → NPU). The NPU decoder has to be exported at a fixed
length, so there is one <voice>.dec_f{N}.pte per length: pick the smallest N ≥ the line's latent
length n, zero-pad to N, and trim the output to n*256 samples. Lines longer than the largest N are
split into sentences; anything that still does not fit goes through the CPU decoder.

Measured on the board (2026-10-18, 7 demo sentences): median HTTP round trip CPU 495 ms / NPU
decoder 373 ms; decoder alone CPU 274 ms / NPU fp16 185 ms (fixed 384), cosine 0.9999 vs CPU.
export: ml/export/export_piper_decoder.py.
"""

import io
import threading
import time
import wave
from pathlib import Path

import numpy as np

from common.config import ROOT

HOP = 256  # Piper medium: 1 latent frame = 256 samples
# Demo voice: 12% faster than default, livelier intonation (defaults 0.667 / 1.0 / 0.8)
NOISE_SCALE, LENGTH_SCALE, NOISE_W = 0.8, 0.88, 0.9
SENTENCE_GAP = 0.15  # silence between sentences (seconds)
PEAK = 0.89  # -1 dBFS


def split_voice(voice_path):
    """voice .onnx → (front.onnx, dec.onnx). Reuses the files if they already exist."""
    import onnx
    from onnx.utils import extract_model

    voice = Path(voice_path)
    front, dec = voice.with_suffix(".front.onnx"), voice.with_suffix(".dec.onnx")
    if not (front.exists() and dec.exists()):
        z = next(n.input[0] for n in onnx.load(str(voice)).graph.node if n.name == "/dec/conv_pre/Conv")
        extract_model(str(voice), str(front), ["input", "input_lengths", "scales"], [z])
        extract_model(str(voice), str(dec), [z], ["output"])
    return front, dec


def to_wav(audio, rate):
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes((np.clip(audio, -1, 1) * 32767).astype(np.int16).tobytes())
    return buf.getvalue()


class PiperTTS:
    def __init__(self, voice_path, decoder_dir="", worker_bin="", runners=None):
        import onnxruntime as ort
        from piper import PiperVoice

        voice = Path(voice_path)
        voice = voice if voice.is_absolute() else ROOT / voice
        self.voice = PiperVoice.load(str(voice))
        self.rate = self.voice.config.sample_rate
        front, dec = split_voice(voice)
        cpu = ["CPUExecutionProvider"]
        self.front = ort.InferenceSession(str(front), providers=cpu)
        self.dec = ort.InferenceSession(str(dec), providers=cpu)
        self.z_name = self.dec.get_inputs()[0].name
        self.scales = np.array([NOISE_SCALE, LENGTH_SCALE, NOISE_W], np.float32)
        self.lock = threading.Lock()
        self.npu = dict(runners or {})  # {frames: runner(run(list[np.ndarray]) -> list[np.ndarray])}
        if not self.npu and decoder_dir:
            from services.vision.resident import ResidentRunner

            d = Path(decoder_dir)
            d = d if d.is_absolute() else ROOT / d
            for pte in sorted(d.glob(f"{voice.stem}.dec_f*.pte")):
                frames = int(pte.stem.rsplit("_f", 1)[1])
                self.npu[frames] = ResidentRunner(worker_bin, pte, (1, 1, 1, frames * HOP))
        self.last = {}

    @property
    def status(self):
        return {
            "decoder": "npu" if self.npu else "cpu",
            "npu_frames": sorted(self.npu),
            "workers": {f: getattr(r, "status", None) for f, r in sorted(self.npu.items())},
            "last": self.last,
        }

    def decode(self, z):
        n = z.shape[2]
        fit = [f for f in sorted(self.npu) if f >= n]
        if fit:
            pad = np.zeros((1, z.shape[1], fit[0]), np.float32)
            pad[:, :, :n] = z
            (out,) = self.npu[fit[0]].run([pad])
            return out.reshape(-1)[: n * HOP], f"npu{fit[0]}"
        (out,) = self.dec.run(None, {self.z_name: z})
        return out.reshape(-1), "cpu"

    def latent(self, ids):
        x = np.array([ids], np.int64)
        (z,) = self.front.run(None, {"input": x, "input_lengths": np.array([x.shape[1]], np.int64),
                                     "scales": self.scales})
        return z.astype(np.float32)

    def synthesize(self, text):
        """text → WAV bytes. Decodes the whole line in one pass (on the NPU if it fits an NPU
        length); lines longer than the largest NPU length are split and decoded per sentence."""
        with self.lock:
            t0 = time.perf_counter()
            sentences = [ids for ids in (self.voice.phonemes_to_ids(p) for p in self.voice.phonemize(text)) if ids]
            if not sentences:
                raise ValueError("Nothing to say")
            t = time.perf_counter()
            z = self.latent([i for ids in sentences for i in ids])
            groups = [z]
            if self.npu and len(sentences) > 1 and z.shape[2] > max(self.npu):
                groups = [self.latent(ids) for ids in sentences]
            front_s = time.perf_counter() - t
            t = time.perf_counter()
            gap = np.zeros(int(SENTENCE_GAP * self.rate), np.float32)
            parts, used = [], []
            for zz in groups:
                audio, how = self.decode(zz)
                parts += [audio, gap]
                used.append(f"{how}:{zz.shape[2]}")
            dec_s = time.perf_counter() - t
            audio = np.concatenate(parts[:-1])
            audio = audio / max(1e-6, float(np.abs(audio).max())) * PEAK
            self.last = dict(decoders=used, front_ms=round(front_s * 1000), decoder_ms=round(dec_s * 1000),
                             total_ms=round((time.perf_counter() - t0) * 1000), seconds=round(audio.size / self.rate, 2))
            return to_wav(audio, self.rate)

    def close(self):
        for r in self.npu.values():
            if hasattr(r, "close"):
                r.close()
