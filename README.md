# qwen-book

Turn an EPUB into a chaptered `.m4b` audiobook using **Qwen3-TTS** through
[MLX Audio](https://github.com/Blaizzy/mlx-audio). Apple Silicon required.
`ffmpeg` required for M4B encoding.

Preview mode synthesizes only a small piece of the book, so you can check the
narrator, speed and pronunciation before committing to a full run.

## Install

```bash
brew install uv ffmpeg      # if not installed
uv sync
```

`uv` reads `.python-version` (3.12) and `uv.lock`. It creates `.venv` and
installs the app plus MLX Audio. Qwen3-TTS is loaded through MLX Audio; no
separate `qwen-tts` package is needed.

Models are downloaded from Hugging Face on first use and cached once in
`~/.cache/huggingface/hub`. Pre-download to avoid waiting later:

```bash
# Default CustomVoice model (~3 GB)
uv run hf download mlx-community/Qwen3-TTS-12Hz-0.6B-CustomVoice-8bit

# Base model for voice cloning (~4.5 GB)
uv run hf download mlx-community/Qwen3-TTS-12Hz-1.7B-Base-bf16
```

Each `--model` caches separately. Use `uv run hf cache ls` to inspect the cache.

## Quick start

```bash
# Small preview: first ~1500 characters -> book.preview.m4b
uv run qwen-book book.epub --preview

# Full book -> book.m4b
uv run qwen-book book.epub

# Explicit output and voice
uv run qwen-book book.epub -o /tmp/book.m4b --voice Aiden
```

Recommended loop:

```bash
uv run qwen-book book.epub --preview --voice Ryan
# listen to book.preview.m4b
uv run qwen-book book.epub --preview --voice Aiden --instruct "Calm, warm narrator."
# then full run
uv run qwen-book book.epub
```

Preview chunks are cached, so a later full run does not regenerate the same
text.

## Useful options

```bash
# Show preset voices and supported languages for the default model
uv run qwen-book --list-voices

# Show them for another model
uv run qwen-book --list-voices --model mlx-community/Qwen3-TTS-12Hz-1.7B-VoiceDesign-4bit

# Preview a specific chapter range (1-indexed, inclusive)
uv run qwen-book book.epub --chapters 3-4 --preview --preview-chars 2500

# Full book, but only chapters 5-8
uv run qwen-book book.epub --chapters 5-8

# VoiceDesign model: describe the voice instead of using a preset speaker
uv run qwen-book book.epub --preview \
  --model mlx-community/Qwen3-TTS-12Hz-1.7B-VoiceDesign-4bit \
  --instruct "A clear, low male narrator with slow pacing."

# Voice cloning with a Base model
# narrator.json: {"text": "Exact transcript of narrator.wav."}
uv run qwen-book book.epub --preview \
  --model mlx-community/Qwen3-TTS-12Hz-1.7B-Base-bf16 \
  --ref-audio narrator.wav --ref-text narrator.json

# Fast heuristic estimate: chapters/chunking/time, no model load
uv run qwen-book book.epub --dry-run

# Real estimate: synthesize ~700 chars, measure speed, extrapolate selected range
uv run qwen-book book.epub --dry-run --calibrate

# Calibrated estimate for a Russian cloned narrator
uv run qwen-book book.epub \
  --language russian \
  --ref-audio narrator.wav \
  --ref-text narrator.json \
  --model mlx-community/Qwen3-TTS-12Hz-1.7B-Base-bf16 \
  --dry-run --calibrate --calibrate-chars 700

# Longer chunks / less frequent pauses
uv run qwen-book book.epub --chunk-chars 350 --pause-ms 300
```

Default CustomVoice speakers: `Ryan`, `Aiden`, `Vivian`, `Serena`,
`Uncle_Fu`, `Dylan`, `Eric`, `Ono_Anna`, `Sohee`. Voice availability depends on
the model.

Language is taken from EPUB metadata (`en` -> `english`, `ru` -> `russian`).
Override with `--language english|russian|chinese|auto|...`.

## What it does

1. Reads spine order from the EPUB, skips nav/cover/non-linear documents.
2. Extracts headings and paragraphs with BeautifulSoup; splits long HTML files
   at repeated `h1`/`h2` headings into audiobook chapters.
3. Normalizes text and packs it into Qwen3-TTS-friendly chunks.
4. Synthesizes each chunk with MLX Audio, caches it by content hash, inserts
   sentence/paragraph/chapter pauses.
5. Concatenates cached WAVs and encodes AAC into M4B with ffmpeg.
6. Embeds EPUB metadata, cover art and a chapter list.

## Output and cache

- Full output: next to the EPUB, `book.m4b`.
- Preview output: `book.preview.m4b`.
- Work/cache directory: `book.work/` next to the EPUB. Preview, calibration and
  full runs share this cache unless `--work-dir` is set.
- Calibration preview: `<output>.calibration.m4b`; measured WAVs in
  `book.work/calibration/`.

Interrupted runs can be resumed by rerunning the same command: finished chunks
come from cache. Changing model, voice, language, instruct, reference audio or
sampling settings invalidates the cache automatically. Once an M4B is finished,
the `*.work/cache/` WAVs are only needed for future resume/retry runs and can be
deleted to save disk space.

`last-run.json` in the work directory records timings and chapter boundaries.

`--dry-run --calibrate` runs a fresh short TTS sample (does not use the chunk
cache), drops first-chunk warmup if it is clearly anomalous, and prints measured
chars/sec, RTF, warmup, and a calibrated estimate for the selected range.

## Notes

- MLX Audio runs on Apple Silicon only.
- M4B chapter names come from EPUB headings, then TOC titles.
- Some EPUBs have very noisy front matter. Use `--chapters` or preview to check
  before a long run.
- The converter is single-voice. Role-based multi-speaker narration is not
  included.

## Development

```bash
uv sync --all-groups
uv run pytest -q
```
