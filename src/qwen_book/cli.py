"""Command line interface for qwen-book."""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

from .epub import read_book
from .pipeline import (
    estimate_range,
    make_plan,
    run_calibration,
    synthesize_and_package,
)
from .text import language_to_qwen
from .tts import TTSEngine, load_ref_text, model_voices

DEFAULT_MODEL = "mlx-community/Qwen3-TTS-12Hz-0.6B-CustomVoice-8bit"
DEFAULT_VOICE = "Ryan"
SYNTH_RTF = 0.5


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="qwen-book",
        description=(
            "Convert an EPUB into a chaptered M4B audiobook with Qwen3-TTS "
            "and MLX Audio."
        ),
    )
    parser.add_argument("book", type=Path, nargs="?", help="input EPUB file")
    parser.add_argument("-o", "--output", type=Path, help="output M4B path")

    model = parser.add_argument_group("voice and model")
    model.add_argument("--model", default=DEFAULT_MODEL, help=f"model id (default: {DEFAULT_MODEL})")
    model.add_argument(
        "--list-voices",
        action="store_true",
        help="list preset voices for --model and exit (does not load weights)",
    )
    model.add_argument(
        "--voice",
        default=None,
        help=f"CustomVoice speaker (default: {DEFAULT_VOICE}; ignored by VoiceDesign)",
    )
    model.add_argument(
        "--language",
        default=None,
        help="Qwen language name/code (default: from EPUB metadata, e.g. english, russian, en)",
    )
    model.add_argument("--instruct", help="emotion/style or VoiceDesign voice description")
    model.add_argument("--ref-audio", type=Path, help="reference WAV for voice cloning (Base models)")
    model.add_argument(
        "--ref-text",
        type=Path,
        help='JSON file with {"text": "exact transcript"} for --ref-audio',
    )
    model.add_argument("--temperature", type=float)
    model.add_argument("--top-p", type=float)
    model.add_argument("--top-k", type=int)
    model.add_argument("--repetition-penalty", type=float)

    text = parser.add_argument_group("text and audio")
    text.add_argument("--chunk-chars", type=int, default=280, help="maximum TTS chunk size (default: 280)")
    text.add_argument("--min-chars", type=int, default=90, help="merge chunks below this size (default: 90)")
    text.add_argument("--pause-ms", type=int, default=250, help="pause after sentences (default: 250)")
    text.add_argument("--paragraph-pause-ms", type=int, default=420, help="pause after paragraphs (default: 420)")
    text.add_argument("--chapter-pause-ms", type=int, default=1200, help="pause between chapters (default: 1200)")
    text.add_argument("--bitrate", default="64k", help="AAC bitrate (default: 64k)")
    text.add_argument("--no-cover", action="store_true", help="do not embed the EPUB cover")

    preview = parser.add_argument_group("preview and selection")
    preview.add_argument(
        "--preview",
        action="store_true",
        help="synthesize only the beginning of the book and write <book>.preview.m4b",
    )
    preview.add_argument(
        "--preview-chars",
        type=int,
        default=1500,
        help="preview text budget in characters (default: 1500)",
    )
    preview.add_argument(
        "--chapters",
        help="1-indexed chapter range, for example 3, 3-5, 5- or -3",
    )
    preview.add_argument(
        "--calibrate",
        action="store_true",
        help="with --dry-run, synthesize a short sample and estimate from measured speed",
    )
    preview.add_argument(
        "--calibrate-chars",
        type=int,
        default=700,
        help="calibration sample size in characters (default: 700)",
    )

    other = parser.add_argument_group("other")
    other.add_argument("--work-dir", type=Path, help="cache/work directory (default: next to output)")
    other.add_argument("--force", action="store_true", help="overwrite an existing M4B")
    other.add_argument(
        "--dry-run",
        action="store_true",
        help="parse and plan; add --calibrate to run a short TTS speed test",
    )
    other.add_argument("--ffmpeg", help="path to ffmpeg")
    other.add_argument("-v", "--verbose", action="store_true", help="print each chunk text")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return _run(args, parser)
    except KeyboardInterrupt:
        print("Interrupted.", file=sys.stderr)
        return 130
    except (OSError, ValueError, RuntimeError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


def _run(args: argparse.Namespace, parser: argparse.ArgumentParser) -> int:
    if args.list_voices:
        return _list_voices(args.model)
    if args.book is None:
        parser.error("book is required unless --list-voices is used")
    if args.calibrate and not args.dry_run:
        parser.error("--calibrate requires --dry-run")
    if args.calibrate and args.calibrate_chars <= 0:
        parser.error("--calibrate-chars must be positive")

    book = read_book(args.book)
    chapter_range = _parse_chapter_range(args.chapters, len(book.chapters))

    if args.ref_text and not args.ref_audio:
        parser.error("--ref-text requires --ref-audio")
    if args.ref_audio and args.voice:
        parser.error("use either --voice or --ref-audio, not both")
    if args.ref_audio and not args.ref_audio.is_file():
        parser.error(f"reference audio not found: {args.ref_audio}")
    ref_text = load_ref_text(args.ref_text) if args.ref_text else None

    voice = args.voice if args.voice is not None else (None if args.ref_audio else DEFAULT_VOICE)
    language = language_to_qwen(args.language) if args.language else book.language
    preview_chars = args.preview_chars if args.preview else None
    if args.preview and preview_chars is not None and preview_chars <= 0:
        parser.error("--preview-chars must be positive")

    output = _output_path(book.path, args.output, preview=args.preview)
    if output.exists() and not args.force and not args.preview and not args.dry_run:
        parser.error(f"output already exists: {output} (use --force to overwrite)")

    if args.no_cover:
        book.cover = None

    plans = _plan(book, args, chapter_range, preview_chars)
    total_chars = sum(plan.char_count for plan in plans)
    total_pauses = _pause_seconds(plans, args.chapter_pause_ms)

    print(f"Book:     {book.title}")
    print(f"Author:   {book.author}")
    print(f"Language: {language} ({book.language_code or 'unknown'})")
    print(f"Chapters: {len(plans)} selected / {len(book.chapters)} total")
    print(f"Text:     {total_chars:,} characters")
    print(f"Output:   {output}")

    if args.dry_run:
        _print_heuristic_estimate(plans, args, total_pauses)
        if not args.calibrate:
            return 0

        work_dir = args.work_dir or _default_work_dir(book.path)
        print(f"\nWork:     {work_dir}")
        tts = _load_tts(args, voice, language, ref_text)

        calibration_limit = args.calibrate_chars
        if args.preview:
            calibration_limit = min(calibration_limit, args.preview_chars)
        calibration_plans = _plan(book, args, chapter_range, calibration_limit)
        calibration_output = output.with_suffix(".calibration.m4b")
        print(f"Preview:  {calibration_output}")

        metrics = run_calibration(
            book,
            calibration_plans,
            tts,
            work_dir,
            calibration_output,
            chapter_pause_ms=args.chapter_pause_ms,
            bitrate=args.bitrate,
            ffmpeg=args.ffmpeg,
        )
        estimate = estimate_range(total_chars, total_pauses, metrics)
        _print_calibrated_estimate(metrics, estimate, calibration_output)
        return 0

    work_dir = args.work_dir or _default_work_dir(book.path)
    print(f"Work:     {work_dir}")
    tts = _load_tts(args, voice, language, ref_text)

    result = synthesize_and_package(
        book,
        plans,
        tts,
        output,
        work_dir,
        chapter_pause_ms=args.chapter_pause_ms,
        bitrate=args.bitrate,
        ffmpeg=args.ffmpeg,
        verbose=args.verbose,
    )

    print()
    print(f"Done: {result.output}")
    print(
        f"Audio: {_human_duration(result.audio_seconds)} | "
        f"chunks: {result.chunk_count} "
        f"({result.generated} new, {result.cached} cached) | "
        f"elapsed: {_human_duration(result.elapsed_seconds)}"
    )
    print(f"Cache: {result.work_dir}")
    if args.preview:
        print("Preview ready. Listen, adjust --voice/--instruct, then run again without --preview.")
    return 0


def _default_work_dir(book_path: Path) -> Path:
    # Keep preview, calibration and full runs on the same cache.
    return book_path.with_suffix(".work")


def _plan(book, args: argparse.Namespace, chapter_range, preview_chars):
    return make_plan(
        book,
        chapter_range=chapter_range,
        preview_chars=preview_chars,
        max_chars=args.chunk_chars,
        min_chars=args.min_chars,
        pause_ms=args.pause_ms,
        paragraph_pause_ms=args.paragraph_pause_ms,
    )


def _pause_seconds(plans, chapter_pause_ms: int) -> float:
    return (
        sum(chunk.pause_after_ms for plan in plans for chunk in plan.chunks) / 1000
        + max(0, len(plans) - 1) * chapter_pause_ms / 1000
    )


def _load_tts(args: argparse.Namespace, voice: str | None, language: str, ref_text: str | None):
    print("Loading Qwen3-TTS model (first run downloads weights)…", flush=True)
    tts = TTSEngine(
        args.model,
        voice=voice,
        language=language,
        instruct=args.instruct,
        ref_audio=args.ref_audio,
        ref_text=ref_text,
        temperature=args.temperature,
        top_p=args.top_p,
        top_k=args.top_k,
        repetition_penalty=args.repetition_penalty,
        verbose=args.verbose,
    )
    print(f"Model ready in {tts.load_seconds:.1f}s; sample rate {tts.sample_rate} Hz.", flush=True)
    return tts


def _print_heuristic_estimate(plans, args: argparse.Namespace, total_pauses: float) -> None:
    cps = _chars_per_second(args.model)
    total_speech = sum(plan.char_count for plan in plans) / cps
    for plan in plans:
        speech = plan.char_count / cps
        pauses = sum(chunk.pause_after_ms for chunk in plan.chunks) / 1000
        print(
            f"  {plan.chapter.index:>3}. {plan.chapter.title} "
            f"({plan.char_count:,} chars, {len(plan.chunks)} chunks, "
            f"~{_human_duration(speech + pauses)} audio, "
            f"~{_human_duration(speech * SYNTH_RTF)} synth)"
        )
    print(
        f"\nEstimate (heuristic): ~{_human_duration(total_speech + total_pauses)} audio | "
        f"~{_human_duration(total_speech * SYNTH_RTF)} synthesis "
        f"({cps:g} chars/s, RTF ~{SYNTH_RTF:g})"
    )
    print("Heuristic: uses model-size defaults. Add --calibrate for measured estimate.")


def _print_calibrated_estimate(metrics, estimate, calibration_output: Path) -> None:
    print()
    print(
        f"Measured: {metrics.chunks} chunk(s) / {metrics.chars:,} chars, "
        f"{_human_duration(metrics.speech_seconds)} audio in "
        f"{_human_duration(metrics.synth_seconds)} synthesis"
    )
    print(
        f"Steady:   {metrics.chars_per_second:.1f} chars/s audio | "
        f"RTF {metrics.rtf:.2f} | warmup {_human_duration(metrics.warmup_seconds)} | "
        f"model load {_human_duration(metrics.model_load_seconds)}"
    )
    if metrics.chunks < 2:
        print("Warning: only one chunk measured; warmup correction not available.")
    print(
        f"Estimate (calibrated): ~{_human_duration(estimate.audio_seconds)} audio | "
        f"~{_human_duration(estimate.synth_seconds)} synthesis"
    )
    print(f"Preview:  {calibration_output}")
    print("Calibrated estimate assumes same speed for the selected range; excludes model load and M4B encoding.")


def _chars_per_second(model_id: str) -> float:
    value = model_id.lower()
    if "0.6b" in value:
        return 15.0
    if "1.7b" in value:
        return 8.0
    return 12.0


def _list_voices(model_id: str) -> int:
    try:
        voices, languages, model_type = model_voices(model_id)
    except Exception as exc:
        print(f"error: could not read model config: {exc}", file=sys.stderr)
        return 1

    print(f"Model: {model_id}")
    if model_type:
        print(f"Type:  {model_type}")
    if voices:
        print("Voices:")
        for voice in voices:
            print(f"  {voice}")
    elif model_type == "voice_design":
        print("Voices: none. Use --instruct to describe the voice.")
    elif model_type == "base":
        print("Voices: none. Use --ref-audio and --ref-text to clone a voice.")
    else:
        print("Voices: none found in model config.")
    if languages:
        print("Languages:")
        for language in languages:
            print(f"  {language}")
    else:
        print("Languages: auto")
    return 0


def _output_path(book_path: Path, requested: Path | None, *, preview: bool) -> Path:
    if requested is not None:
        output = requested
    elif preview:
        output = book_path.with_name(f"{book_path.stem}.preview.m4b")
    else:
        output = book_path.with_suffix(".m4b")
    if output.suffix.lower() != ".m4b":
        output = output.with_suffix(".m4b")
    return output


def _parse_chapter_range(value: str | None, count: int) -> tuple[int, int] | None:
    if not value:
        return None
    value = value.strip()
    if value.isdigit():
        start = end = int(value)
    else:
        match = re.fullmatch(r"(\d+)?-(\d+)?", value)
        if not match or not (match.group(1) or match.group(2)):
            raise ValueError(f"invalid chapter range: {value!r} (try 3, 3-5, 5- or -3)")
        start = int(match.group(1) or 1)
        end = int(match.group(2) or count)
    if start < 1 or end < 1 or start > end:
        raise ValueError(f"invalid chapter range: {value!r}")
    if end > count:
        raise ValueError(f"chapter range ends at {end}, but the book has {count} chapters")
    return start, end


def _human_duration(seconds: float) -> str:
    total = max(0, round(seconds))
    hours, remainder = divmod(total, 3600)
    minutes, secs = divmod(remainder, 60)
    if hours:
        return f"{hours}h {minutes:02d}m {secs:02d}s"
    if minutes:
        return f"{minutes}m {secs:02d}s"
    return f"{secs}s"


if __name__ == "__main__":
    raise SystemExit(main())
