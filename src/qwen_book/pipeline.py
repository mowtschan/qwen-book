"""Synthesis and packaging pipeline."""

from __future__ import annotations

import hashlib
import json
import time
from dataclasses import dataclass
from statistics import median
from pathlib import Path

from .audio import read_wav_info, write_silence, write_wav
from .epub import Book, Chapter
from .m4b import AudioPart, ChapterMark, build_m4b
from .text import SpeechChunk, chunk_blocks, limit_chunks

CACHE_VERSION = 1


@dataclass
class ChapterPlan:
    chapter: Chapter
    chunks: list[SpeechChunk]

    @property
    def char_count(self) -> int:
        return sum(len(chunk.text) for chunk in self.chunks)


@dataclass
class SynthesisResult:
    output: Path
    work_dir: Path
    chapters: list[ChapterMark]
    chunk_count: int
    generated: int
    cached: int
    audio_seconds: float
    elapsed_seconds: float


@dataclass
class CalibrationMetrics:
    chunks: int
    chars: int
    speech_seconds: float
    synth_seconds: float
    chars_per_second: float
    rtf: float
    warmup_seconds: float
    model_load_seconds: float = 0.0


@dataclass
class TimeEstimate:
    speech_seconds: float
    pause_seconds: float
    audio_seconds: float
    synth_seconds: float


def compute_calibration(
    chars: list[int],
    speech_seconds: list[float],
    synth_seconds: list[float],
) -> CalibrationMetrics:
    """Measure speech rate and steady-state synthesis RTF from real chunks."""
    if not chars or len(chars) != len(speech_seconds) or len(chars) != len(synth_seconds):
        raise ValueError("Calibration measurements must be non-empty and aligned")

    samples = [
        (int(count), float(speech), float(synth))
        for count, speech, synth in zip(chars, speech_seconds, synth_seconds)
        if speech > 0 and synth > 0
    ]
    if not samples:
        raise ValueError("Calibration produced no measurable audio")

    total_chars = sum(sample[0] for sample in samples)
    total_speech = sum(sample[1] for sample in samples)
    total_synth = sum(sample[2] for sample in samples)
    include = list(range(len(samples)))
    warmup = 0.0

    if len(samples) >= 2:
        ratios = [sample[2] / sample[1] for sample in samples]
        baseline = median(ratios[1:])
        if baseline > 0 and ratios[0] > baseline * 2.0:
            # First chunk often pays one-time Metal compilation. Drop it from RTF
            # and charge that overhead once in the final estimate.
            include = list(range(1, len(samples)))
            warmup = max(0.0, samples[0][2] - baseline * samples[0][1])

    steady_speech = sum(samples[index][1] for index in include)
    steady_synth = sum(samples[index][2] for index in include)
    rtf = steady_synth / steady_speech if steady_speech > 0 else total_synth / total_speech

    return CalibrationMetrics(
        chunks=len(samples),
        chars=total_chars,
        speech_seconds=total_speech,
        synth_seconds=total_synth,
        chars_per_second=total_chars / total_speech,
        rtf=rtf,
        warmup_seconds=warmup,
    )


def estimate_range(
    total_chars: int,
    pause_seconds: float,
    metrics: CalibrationMetrics,
) -> TimeEstimate:
    """Extrapolate calibrated speed to a planned chapter range."""
    if total_chars <= 0:
        raise ValueError("Cannot estimate an empty range")
    speech = total_chars / metrics.chars_per_second
    return TimeEstimate(
        speech_seconds=speech,
        pause_seconds=pause_seconds,
        audio_seconds=speech + pause_seconds,
        synth_seconds=speech * metrics.rtf + metrics.warmup_seconds,
    )


def select_chapters(book: Book, chapter_range: tuple[int, int] | None) -> list[Chapter]:
    if chapter_range is None:
        return list(book.chapters)
    start, end = chapter_range
    if start < 1 or end > len(book.chapters) or start > end:
        raise ValueError(
            f"Chapter range {start}-{end} is outside 1-{len(book.chapters)}"
        )
    return book.chapters[start - 1 : end]


def make_plan(
    book: Book,
    *,
    chapter_range: tuple[int, int] | None = None,
    preview_chars: int | None = None,
    max_chars: int = 280,
    min_chars: int = 90,
    pause_ms: int = 250,
    paragraph_pause_ms: int = 420,
    chapter_head_pause_ms: int = 700,
) -> list[ChapterPlan]:
    """Split selected chapters into TTS chunks, optionally limited by character count."""
    plans: list[ChapterPlan] = []
    used_chars = 0

    for chapter in select_chapters(book, chapter_range):
        chunks = chunk_blocks(
            chapter.blocks,
            max_chars=max_chars,
            min_chars=min_chars,
            pause_ms=pause_ms,
            paragraph_pause_ms=paragraph_pause_ms,
            chapter_head_pause_ms=chapter_head_pause_ms,
        )
        if preview_chars and preview_chars > 0:
            remaining = preview_chars - used_chars
            if remaining <= 0:
                break
            chunks = limit_chunks(chunks, remaining)
        if chunks:
            plans.append(ChapterPlan(chapter=chapter, chunks=chunks))
            used_chars += sum(len(chunk.text) for chunk in chunks)

    if not plans:
        raise ValueError("No text to synthesize for the selected range")
    return plans


def synthesize_and_package(
    book: Book,
    plans: list[ChapterPlan],
    tts,
    output: str | Path,
    work_dir: str | Path,
    *,
    chapter_pause_ms: int = 1200,
    bitrate: str = "64k",
    ffmpeg: str | None = None,
    verbose: bool = False,
) -> SynthesisResult:
    output = Path(output)
    work_dir = Path(work_dir)
    cache_dir = work_dir / "cache"
    silence_dir = work_dir / "silence"
    cache_dir.mkdir(parents=True, exist_ok=True)
    silence_dir.mkdir(parents=True, exist_ok=True)

    started = time.perf_counter()
    settings = _settings_key(tts)
    sample_rate = int(tts.sample_rate)
    total_chunks = sum(len(plan.chunks) for plan in plans)
    total_chars = sum(plan.char_count for plan in plans)
    print(
        f"Synthesizing {total_chunks} chunks / {total_chars:,} characters "
        f"across {len(plans)} chapter(s).",
        flush=True,
    )

    parts: list[AudioPart] = []
    marks: list[ChapterMark] = []
    generated = 0
    cached = 0
    total_frames = 0
    chunk_index = 0
    silence_cache: dict[int, AudioPart] = {}

    try:
        for plan_index, plan in enumerate(plans):
            chapter_start = total_frames
            for chunk in plan.chunks:
                chunk_index += 1
                key = _chunk_key(settings, chunk.text)
                wav_path = cache_dir / key[:2] / f"{key}.wav"
                if _valid_cache(wav_path, sample_rate):
                    info = read_wav_info(wav_path)
                    cached += 1
                    state = "cached"
                else:
                    audio = tts.synthesize(chunk.text)
                    info = write_wav(wav_path, audio, sample_rate)
                    generated += 1
                    state = "new"

                part = AudioPart(path=wav_path, info=info)
                parts.append(part)
                total_frames += info.frames

                if chunk.pause_after_ms > 0:
                    part = _silence_part(silence_dir, sample_rate, chunk.pause_after_ms, silence_cache)
                    parts.append(part)
                    total_frames += part.info.frames

                print(
                    f"[{chunk_index}/{total_chunks}] {plan.chapter.title[:60]!r} "
                    f"{len(chunk.text):>4} chars {state:>6} "
                    f"audio={total_frames / sample_rate:,.1f}s",
                    flush=True,
                )
                if verbose:
                    print(f"    {chunk.text}", flush=True)

            marks.append(
                ChapterMark(
                    title=plan.chapter.title,
                    start_frames=chapter_start,
                    end_frames=total_frames,
                )
            )

            if plan_index < len(plans) - 1 and chapter_pause_ms > 0:
                part = _silence_part(silence_dir, sample_rate, chapter_pause_ms, silence_cache)
                parts.append(part)
                total_frames += part.info.frames

        # Each chapter ends where the next begins, so inter-chapter silence belongs
        # to the previous chapter and the whole timeline is covered.
        for index, mark in enumerate(marks[:-1]):
            marks[index] = ChapterMark(
                title=mark.title,
                start_frames=mark.start_frames,
                end_frames=marks[index + 1].start_frames,
            )
        marks[-1] = ChapterMark(
            title=marks[-1].title,
            start_frames=marks[-1].start_frames,
            end_frames=total_frames,
        )

        if generated == 0:
            print("All chunks came from cache; encoding M4B.", flush=True)

        cover = (book.cover.data, book.cover.media_type) if book.cover else None
        build_m4b(
            parts,
            marks,
            output,
            title=book.title,
            author=book.author,
            cover=cover,
            bitrate=bitrate,
            ffmpeg=ffmpeg,
        )
    except KeyboardInterrupt:
        print(f"\nInterrupted. Cached chunks are kept in {work_dir}", flush=True)
        raise

    elapsed = time.perf_counter() - started
    result = SynthesisResult(
        output=output,
        work_dir=work_dir,
        chapters=marks,
        chunk_count=total_chunks,
        generated=generated,
        cached=cached,
        audio_seconds=total_frames / sample_rate,
        elapsed_seconds=elapsed,
    )
    _write_manifest(book, result, plans, tts, output)
    return result


def run_calibration(
    book: Book,
    plans: list[ChapterPlan],
    tts,
    work_dir: str | Path,
    output: str | Path,
    *,
    chapter_pause_ms: int = 1200,
    bitrate: str = "64k",
    ffmpeg: str | None = None,
) -> CalibrationMetrics:
    """Synthesize a short sample, measure real speed, and write a preview M4B."""
    output = Path(output)
    work_dir = Path(work_dir)
    calibration_dir = work_dir / "calibration"
    cache_dir = work_dir / "cache"
    calibration_dir.mkdir(parents=True, exist_ok=True)
    cache_dir.mkdir(parents=True, exist_ok=True)
    settings = _settings_key(tts)

    total_items = sum(len(plan.chunks) for plan in plans)
    total_chars = sum(plan.char_count for plan in plans)
    print(
        f"Calibrating with {total_items} chunk(s) / {total_chars:,} characters",
        flush=True,
    )

    parts: list[AudioPart] = []
    chars: list[int] = []
    speech_seconds: list[float] = []
    synth_seconds: list[float] = []
    silence_cache: dict[int, AudioPart] = {}
    total_frames = 0
    index = 0

    for plan_index, plan in enumerate(plans):
        for chunk in plan.chunks:
            index += 1
            started = time.perf_counter()
            audio = tts.synthesize(chunk.text)
            synth_time = time.perf_counter() - started
            wav_path = calibration_dir / f"{index:03d}.wav"
            info = write_wav(wav_path, audio, tts.sample_rate)
            # Populate the normal chunk cache too, so a later preview/full run
            # can reuse these exact chunks.
            cache_key = _chunk_key(settings, chunk.text)
            write_wav(cache_dir / cache_key[:2] / f"{cache_key}.wav", audio, tts.sample_rate)
            parts.append(AudioPart(path=wav_path, info=info))
            total_frames += info.frames
            chars.append(len(chunk.text))
            speech_seconds.append(info.frames / tts.sample_rate)
            synth_seconds.append(synth_time)
            print(
                f"  [{index}/{total_items}] {len(chunk.text):>4} chars "
                f"-> {info.frames / tts.sample_rate:>5.1f}s audio, "
                f"{synth_time:>6.1f}s synth",
                flush=True,
            )

            if chunk.pause_after_ms > 0:
                part = _silence_part(
                    calibration_dir, tts.sample_rate, chunk.pause_after_ms, silence_cache
                )
                parts.append(part)
                total_frames += part.info.frames

        if plan_index < len(plans) - 1 and chapter_pause_ms > 0:
            part = _silence_part(
                calibration_dir, tts.sample_rate, chapter_pause_ms, silence_cache
            )
            parts.append(part)
            total_frames += part.info.frames

    cover = (book.cover.data, book.cover.media_type) if book.cover else None
    build_m4b(
        parts,
        [ChapterMark("Calibration preview", 0, total_frames)],
        output,
        title=f"{book.title} (calibration preview)",
        author=book.author,
        cover=cover,
        bitrate=bitrate,
        ffmpeg=ffmpeg,
    )

    metrics = compute_calibration(chars, speech_seconds, synth_seconds)
    metrics.model_load_seconds = float(getattr(tts, "load_seconds", 0.0))
    return metrics


def _settings_key(tts) -> dict[str, object]:
    ref_hash = None
    if tts.ref_audio:
        ref_hash = _file_hash(Path(tts.ref_audio))
    return {
        "v": CACHE_VERSION,
        "model": tts.model_id,
        "voice": tts.voice,
        "language": tts.language,
        "instruct": tts.instruct,
        "ref_audio": ref_hash,
        "ref_text": tts.ref_text,
        "temperature": tts.temperature,
        "top_p": tts.top_p,
        "top_k": tts.top_k,
        "repetition_penalty": tts.repetition_penalty,
    }


def _chunk_key(settings: dict[str, object], text: str) -> str:
    payload = dict(settings)
    payload["text"] = text
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _file_hash(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _valid_cache(path: Path, sample_rate: int) -> bool:
    if not path.is_file() or path.stat().st_size <= 44:
        return False
    try:
        info = read_wav_info(path)
    except (OSError, EOFError, ValueError):
        return False
    return info.channels == 1 and info.sample_rate == sample_rate and info.frames > 0


def _silence_part(
    silence_dir: Path,
    sample_rate: int,
    duration_ms: int,
    cache: dict[int, AudioPart],
) -> AudioPart:
    if duration_ms not in cache:
        path = silence_dir / f"silence-{duration_ms}ms.wav"
        if not _valid_cache(path, sample_rate):
            info = write_silence(path, sample_rate, duration_ms)
        else:
            info = read_wav_info(path)
        cache[duration_ms] = AudioPart(path=path, info=info)
    return cache[duration_ms]


def _write_manifest(
    book: Book,
    result: SynthesisResult,
    plans: list[ChapterPlan],
    tts,
    output: Path,
) -> None:
    manifest = {
        "book": {
            "path": str(book.path),
            "title": book.title,
            "author": book.author,
            "language": book.language,
            "language_code": book.language_code,
        },
        "output": str(output),
        "model": tts.model_id,
        "voice": tts.voice,
        "instruct": tts.instruct,
        "chunk_count": result.chunk_count,
        "generated": result.generated,
        "cached": result.cached,
        "audio_seconds": round(result.audio_seconds, 3),
        "elapsed_seconds": round(result.elapsed_seconds, 2),
        "chapters": [
            {
                "title": plan.chapter.title,
                "chars": plan.char_count,
                "chunks": len(plan.chunks),
                "start_seconds": round(mark.start_frames / tts.sample_rate, 3),
                "end_seconds": round(mark.end_frames / tts.sample_rate, 3),
            }
            for plan, mark in zip(plans, result.chapters)
        ],
    }
    (result.work_dir / "last-run.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
