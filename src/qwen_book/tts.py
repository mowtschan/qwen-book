"""Qwen3-TTS adapter built on MLX Audio."""

from __future__ import annotations

import time
from pathlib import Path

import numpy as np


class TTSEngine:
    """Small wrapper around mlx-audio's Qwen3-TTS model."""

    def __init__(
        self,
        model_id: str,
        *,
        voice: str | None = None,
        language: str = "auto",
        instruct: str | None = None,
        ref_audio: str | Path | None = None,
        ref_text: str | None = None,
        temperature: float | None = None,
        top_p: float | None = None,
        top_k: int | None = None,
        repetition_penalty: float | None = None,
        verbose: bool = False,
    ) -> None:
        self.model_id = model_id
        self.voice = voice
        self.language = language
        self.instruct = instruct
        self.ref_audio = str(ref_audio) if ref_audio else None
        self.ref_text = ref_text
        self.temperature = temperature
        self.top_p = top_p
        self.top_k = top_k
        self.repetition_penalty = repetition_penalty
        self.verbose = verbose

        if self.ref_audio and not Path(self.ref_audio).is_file():
            raise FileNotFoundError(f"Reference audio not found: {self.ref_audio}")

        try:
            from mlx_audio.tts.utils import load_model
        except ImportError as exc:
            raise RuntimeError(
                "mlx-audio is not installed. Run `uv sync` or `pip install mlx-audio`."
            ) from exc

        started = time.perf_counter()
        self.model = load_model(model_id)
        self.load_seconds = time.perf_counter() - started
        self.sample_rate = int(getattr(self.model, "sample_rate", 24000))

        model_type = getattr(getattr(self.model, "config", None), "tts_model_type", None)
        self.model_type = model_type or "base"
        if self.model_type == "voice_design":
            # The preset speaker argument is ignored by VoiceDesign models.
            self.voice = None
        if self.model_type == "voice_design" and not self.instruct:
            raise ValueError(
                "VoiceDesign models need --instruct, for example "
                '--instruct "A warm, clear male narrator voice."'
            )
        if self.model_type == "custom_voice" and not self.voice:
            raise ValueError(
                "CustomVoice models need --voice, for example --voice Ryan"
            )
        if self.model_type == "custom_voice" and self.ref_audio:
            raise ValueError(
                "CustomVoice models do not use --ref-audio; "
                "use a Base model for voice cloning"
            )
        if self.model_type == "voice_design" and self.ref_audio:
            raise ValueError("--ref-audio requires a Base model")
        if self.ref_text and not self.ref_audio:
            raise ValueError("--ref-text requires --ref-audio")

    def synthesize(self, text: str) -> np.ndarray:
        """Generate mono float32 audio for one text chunk."""
        kwargs: dict[str, object] = {
            "text": text,
            "lang_code": self.language,
            "stream": False,
            "verbose": self.verbose,
        }
        if self.voice:
            kwargs["voice"] = self.voice
        if self.instruct:
            kwargs["instruct"] = self.instruct
        if self.ref_audio:
            kwargs["ref_audio"] = self.ref_audio
        if self.ref_text:
            kwargs["ref_text"] = self.ref_text
        if self.temperature is not None:
            kwargs["temperature"] = self.temperature
        if self.top_p is not None:
            kwargs["top_p"] = self.top_p
        if self.top_k is not None:
            kwargs["top_k"] = self.top_k
        if self.repetition_penalty is not None:
            kwargs["repetition_penalty"] = self.repetition_penalty

        results = list(self.model.generate(**kwargs))
        parts: list[np.ndarray] = []
        for result in results:
            audio = np.asarray(result.audio, dtype=np.float32).reshape(-1)
            if audio.size:
                parts.append(audio)

        if not parts:
            raise RuntimeError("Qwen3-TTS returned no audio for this chunk")

        audio = np.concatenate(parts)
        audio = np.nan_to_num(audio, nan=0.0, posinf=0.0, neginf=0.0)
        audio = np.clip(audio, -1.0, 1.0)
        return _fade_edges(audio, self.sample_rate, fade_ms=6)


def _fade_edges(audio: np.ndarray, sample_rate: int, *, fade_ms: int) -> np.ndarray:
    """Short fades prevent clicks when independently generated chunks are joined."""
    fade = int(sample_rate * fade_ms / 1000)
    if fade <= 1 or audio.size <= fade * 2:
        return audio
    result = audio.copy()
    ramp = np.linspace(0.0, 1.0, fade, dtype=np.float32)
    result[:fade] *= ramp
    result[-fade:] *= ramp[::-1]
    return result


def model_voices(model_id: str) -> tuple[list[str], list[str], str]:
    """Read preset speakers/languages from a Qwen3-TTS config without loading weights."""
    import json

    model_path = Path(model_id).expanduser()
    if model_path.is_dir():
        config_path = model_path / "config.json"
    else:
        from huggingface_hub import hf_hub_download

        config_path = Path(hf_hub_download(repo_id=model_id, filename="config.json"))

    config = json.loads(config_path.read_text(encoding="utf-8"))
    talker = config.get("talker_config") or {}
    speakers = talker.get("spk_id") or config.get("spk_id") or {}
    language_ids = talker.get("codec_language_id") or config.get("codec_language_id") or {}
    languages = sorted(
        name for name in language_ids if "dialect" not in name
    )
    model_type = config.get("tts_model_type") or talker.get("tts_model_type") or ""
    return sorted(str(name) for name in speakers), languages, str(model_type)


def load_ref_text(path: str | Path) -> str:
    """Load exact reference transcript from a JSON file.

    Expected shape:
        {"text": "exact transcript"}
    Also accepts "ref_text" or "transcript" as the key.
    """
    import json

    path = Path(path)
    if not path.is_file():
        raise FileNotFoundError(f"reference transcript not found: {path}")
    try:
        data = json.loads(path.read_text(encoding="utf-8-sig"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"invalid JSON in {path}: {exc}") from exc

    if isinstance(data, str):
        text = data
    elif isinstance(data, dict):
        text = ""
        for key in ("text", "ref_text", "transcript"):
            value = data.get(key)
            if isinstance(value, str) and value.strip():
                text = value
                break
        if not text:
            raise ValueError(f"{path} must contain a non-empty 'text' field")
    else:
        raise ValueError(f"{path} must contain a JSON object with a 'text' field")

    text = text.strip()
    if not text:
        raise ValueError(f"{path} contains an empty transcript")
    return text
