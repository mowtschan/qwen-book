"""Minimal WAV helpers using only the standard library."""

from __future__ import annotations

import wave
from dataclasses import dataclass
from pathlib import Path

import numpy as np


@dataclass(frozen=True)
class WavInfo:
    channels: int
    sample_rate: int
    frames: int

    @property
    def duration(self) -> float:
        return self.frames / self.sample_rate


def write_wav(path: str | Path, audio: np.ndarray, sample_rate: int) -> WavInfo:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    samples = _to_pcm16(audio)
    with wave.open(str(path), "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(int(sample_rate))
        handle.writeframes(samples.tobytes())
    return WavInfo(channels=1, sample_rate=int(sample_rate), frames=int(samples.size))


def write_silence(path: str | Path, sample_rate: int, duration_ms: int) -> WavInfo:
    frames = max(0, round(int(sample_rate) * max(0, duration_ms) / 1000))
    return write_wav(path, np.zeros(frames, dtype=np.float32), sample_rate)


def read_wav_info(path: str | Path) -> WavInfo:
    with wave.open(str(path), "rb") as handle:
        return WavInfo(
            channels=handle.getnchannels(),
            sample_rate=handle.getframerate(),
            frames=handle.getnframes(),
        )


def _to_pcm16(audio: np.ndarray) -> np.ndarray:
    audio = np.asarray(audio, dtype=np.float32).reshape(-1)
    audio = np.nan_to_num(audio, nan=0.0, posinf=0.0, neginf=0.0)
    audio = np.clip(audio, -1.0, 1.0)
    return np.rint(audio * 32767.0).astype("<i2")
