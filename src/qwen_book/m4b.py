"""M4B packaging with chapter metadata and optional cover art."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path

from .audio import WavInfo, read_wav_info


@dataclass(frozen=True)
class AudioPart:
    path: Path
    info: WavInfo


@dataclass(frozen=True)
class ChapterMark:
    title: str
    start_frames: int
    end_frames: int


def build_m4b(
    parts: list[AudioPart],
    chapters: list[ChapterMark],
    output: str | Path,
    *,
    title: str,
    author: str,
    cover: tuple[bytes, str] | None = None,
    bitrate: str = "64k",
    ffmpeg: str | None = None,
) -> Path:
    """Concatenate WAV parts and encode a chaptered M4B."""
    if not parts:
        raise ValueError("No audio parts to encode")
    if not chapters:
        raise ValueError("At least one chapter is required")

    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    ffmpeg_exe = ffmpeg or shutil.which("ffmpeg")
    if not ffmpeg_exe:
        raise RuntimeError("ffmpeg not found. Install it with `brew install ffmpeg`.")

    infos = [part.info for part in parts]
    sample_rate = infos[0].sample_rate
    channels = infos[0].channels
    for part in parts:
        if part.info.sample_rate != sample_rate or part.info.channels != channels:
            raise ValueError(f"Audio format mismatch in {part.path}")
    total_frames = sum(part.info.frames for part in parts)
    if total_frames <= 0:
        raise ValueError("Audio track is empty")

    _validate_chapters(chapters, total_frames)

    suffix = output.suffix or ".m4b"
    with tempfile.TemporaryDirectory(prefix="qwen-book-", dir=output.parent) as folder_name:
        folder = Path(folder_name)
        concat_file = folder / "audio.ffconcat"
        metadata_file = folder / "chapters.ffmetadata"
        temp_output = folder / f"output{suffix}"

        concat_file.write_text(_concat_list(parts), encoding="utf-8")
        metadata_file.write_text(_ffmetadata(title, author, chapters, sample_rate), encoding="utf-8")

        command = [
            ffmpeg_exe,
            "-hide_banner",
            "-loglevel",
            "error",
            "-y",
            "-f",
            "concat",
            "-safe",
            "0",
            "-i",
            str(concat_file),
            "-f",
            "ffmetadata",
            "-i",
            str(metadata_file),
        ]

        cover_path: Path | None = None
        if cover is not None:
            cover_data, media_type = cover
            cover_suffix = _cover_suffix(media_type)
            cover_path = folder / f"cover{cover_suffix}"
            cover_path.write_bytes(cover_data)
            command += ["-i", str(cover_path)]
            command += ["-map", "2:v:0"]
            if cover_suffix in {".jpg", ".jpeg"}:
                command += ["-c:v", "copy"]
            else:
                command += ["-c:v", "mjpeg", "-pix_fmt", "yuvj420p"]
            command += ["-disposition:v:0", "attached_pic"]

        command += [
            "-map",
            "0:a:0",
            "-map_metadata",
            "1",
            "-map_chapters",
            "1",
            "-c:a",
            "aac",
            "-b:a",
            bitrate,
            "-ac",
            str(channels),
            "-ar",
            str(sample_rate),
            "-movflags",
            "+faststart",
            "-f",
            "mp4",
            str(temp_output),
        ]

        subprocess.run(command, check=True)
        _verify_m4b(temp_output, total_frames / sample_rate, len(chapters), bool(cover))
        os.replace(temp_output, output)

    return output


def probe_m4b(path: str | Path) -> dict:
    ffprobe = shutil.which("ffprobe")
    if not ffprobe:
        return {}
    result = subprocess.run(
        [
            ffprobe,
            "-v",
            "error",
            "-show_format",
            "-show_streams",
            "-show_chapters",
            "-of",
            "json",
            str(path),
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    return json.loads(result.stdout)


def _validate_chapters(chapters: list[ChapterMark], total_frames: int) -> None:
    previous_end = 0
    for chapter in chapters:
        if chapter.start_frames < previous_end:
            raise ValueError(f"Chapter overlaps previous chapter: {chapter.title!r}")
        if chapter.end_frames <= chapter.start_frames:
            raise ValueError(f"Chapter has no audio: {chapter.title!r}")
        previous_end = chapter.end_frames
    if chapters[-1].end_frames != total_frames:
        raise ValueError("Last chapter does not end at the end of the audio")


def _concat_list(parts: list[AudioPart]) -> str:
    lines = ["ffconcat version 1.0"]
    for part in parts:
        lines.append(f"file {_concat_quote(part.path)}")
    return "\n".join(lines) + "\n"


def _concat_quote(path: Path) -> str:
    value = str(path.resolve()).replace("'", "'\\''")
    return f"'{value}'"


def _ffmetadata(
    title: str,
    author: str,
    chapters: list[ChapterMark],
    sample_rate: int,
) -> str:
    lines = [
        ";FFMETADATA1",
        f"title={_escape(title)}",
        f"artist={_escape(author)}",
        f"album={_escape(title)}",
        "genre=Audiobook",
        "comment=Generated with Qwen3-TTS and MLX Audio",
    ]
    for chapter in chapters:
        start = round(chapter.start_frames * 1000 / sample_rate)
        end = round(chapter.end_frames * 1000 / sample_rate)
        lines.extend(
            [
                "[CHAPTER]",
                "TIMEBASE=1/1000",
                f"START={start}",
                f"END={end}",
                f"title={_escape(chapter.title)}",
            ]
        )
    return "\n".join(lines) + "\n"


def _escape(value: str) -> str:
    value = str(value).replace("\\", "\\\\").replace("\r", "").replace("\n", "\\n")
    for char in ("=", ";", "#"):
        value = value.replace(char, "\\" + char)
    return value


def _cover_suffix(media_type: str) -> str:
    mapping = {
        "image/jpeg": ".jpg",
        "image/jpg": ".jpg",
        "image/png": ".png",
        "image/webp": ".webp",
        "image/gif": ".gif",
        "image/bmp": ".bmp",
    }
    return mapping.get(media_type.lower(), ".jpg")


def _verify_m4b(path: Path, expected_duration: float, chapter_count: int, has_cover: bool) -> None:
    if not path.is_file() or path.stat().st_size == 0:
        raise RuntimeError("ffmpeg produced an empty M4B file")

    info = probe_m4b(path)
    if not info:
        return

    duration = float((info.get("format") or {}).get("duration") or 0)
    if duration and abs(duration - expected_duration) > max(1.0, expected_duration * 0.02):
        raise RuntimeError(
            f"M4B duration mismatch: got {duration:.1f}s, expected {expected_duration:.1f}s"
        )

    if len(info.get("chapters") or []) != chapter_count:
        raise RuntimeError("M4B chapter count does not match the book")

    streams = info.get("streams") or []
    if not any(stream.get("codec_name") == "aac" for stream in streams):
        raise RuntimeError("M4B does not contain an AAC audio stream")
    if has_cover and not any(
        (stream.get("disposition") or {}).get("attached_pic") for stream in streams
    ):
        raise RuntimeError("Cover art was not embedded in the M4B")


def wav_part(path: str | Path) -> AudioPart:
    path = Path(path)
    return AudioPart(path=path, info=read_wav_info(path))
