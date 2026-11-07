# Graph Report - qwen-book  (2026-11-07)

## Corpus Check
- 20 files · ~7,915 words
- Verdict: corpus is large enough that graph structure adds value.

## Summary
- 177 nodes · 420 edges · 14 communities (12 shown, 2 thin omitted)
- Extraction: 95% EXTRACTED · 5% INFERRED · 0% AMBIGUOUS · INFERRED: 23 edges (avg confidence: 0.5)
- Token cost: 0 input · 0 output

## Community Hubs (Navigation)
- cli.py
- epub.py
- pipeline.py
- text.py
- m4b.py
- main
- qwen-book
- sample_epub
- __init__.py
- qwen-book
- compute_calibration
- load_ref_text
- TTSEngine
- model_voices

## God Nodes (most connected - your core abstractions)
1. `_run()` - 20 edges
2. `read_book()` - 19 edges
3. `synthesize_and_package()` - 17 edges
4. `run_calibration()` - 16 edges
5. `AudioPart` - 15 edges
6. `build_m4b()` - 15 edges
7. `ChapterMark` - 14 edges
8. `Book` - 13 edges
9. `write_wav()` - 11 edges
10. `ChapterPlan` - 11 edges

## Surprising Connections (you probably didn't know these)
- `test_language_mapping()` --calls--> `language_to_qwen()`  [EXTRACTED]
  tests/test_text.py → src/qwen_book/text.py
- `test_cli_calibrate_requires_dry_run()` --calls--> `main()`  [EXTRACTED]
  tests/test_cli.py → src/qwen_book/cli.py
- `test_cli_dry_run()` --calls--> `main()`  [EXTRACTED]
  tests/test_cli.py → src/qwen_book/cli.py
- `test_cli_dry_run_with_reference_json()` --calls--> `main()`  [EXTRACTED]
  tests/test_cli.py → src/qwen_book/cli.py
- `test_cli_rejects_bad_chapter_range()` --calls--> `main()`  [EXTRACTED]
  tests/test_cli.py → src/qwen_book/cli.py

## Import Cycles
- None detected.

## Communities (14 total, 2 thin omitted)

### Community 0 - "cli.py"
Cohesion: 0.30
Nodes (14): Namespace, _chars_per_second(), _default_work_dir(), _human_duration(), _load_tts(), _output_path(), _parse_chapter_range(), _pause_seconds() (+6 more)

### Community 1 - "epub.py"
Cohesion: 0.15
Nodes (26): _add_toc(), Block, _chapter_title(), _clean_inline(), Cover, extract_blocks(), _find_cover(), _find_item_by_href() (+18 more)

### Community 2 - "pipeline.py"
Cohesion: 0.22
Nodes (21): Book, Chapter, CalibrationMetrics, ChapterPlan, _chunk_key(), estimate_range(), _file_hash(), Path (+13 more)

### Community 3 - "text.py"
Cohesion: 0.13
Nodes (21): make_plan(), Split selected chapters into TTS chunks, optionally limited by character count., chunk_blocks(), limit_chunks(), _merge_pieces(), normalize_text(), Text normalization and chunking for TTS., Keep whole chunks without exceeding the character budget. (+13 more)

### Community 4 - "m4b.py"
Cohesion: 0.16
Nodes (26): parametrize, ndarray, Path, Minimal WAV helpers using only the standard library., read_wav_info(), _to_pcm16(), WavInfo, write_silence() (+18 more)

### Community 5 - "main"
Cohesion: 0.31
Nodes (7): ArgumentParser, build_parser(), main(), test_cli_calibrate_requires_dry_run(), test_cli_dry_run(), test_cli_dry_run_with_reference_json(), test_cli_rejects_bad_chapter_range()

### Community 6 - "qwen-book"
Cohesion: 0.25
Nodes (7): Install, Notes, Output and cache, Quick start, qwen-book, Useful options, What it does

### Community 7 - "sample_epub"
Cohesion: 0.50
Nodes (3): fixture, Path, sample_epub()

### Community 10 - "compute_calibration"
Cohesion: 0.43
Nodes (6): compute_calibration(), Measure speech rate and steady-state synthesis RTF from real chunks., test_compute_calibration_drops_first_chunk_warmup(), test_compute_calibration_keeps_normal_first_chunk(), test_compute_calibration_rejects_empty(), test_estimate_range_adds_pauses_and_warmup()

### Community 11 - "load_ref_text"
Cohesion: 0.33
Nodes (7): load_ref_text(), Qwen3-TTS adapter built on MLX Audio., Load exact reference transcript from a JSON file. Expected shape: {"text":…, test_load_ref_text_accepts_alternate_key(), test_load_ref_text_from_json(), test_load_ref_text_rejects_invalid_json(), test_load_ref_text_rejects_missing_field()

### Community 12 - "TTSEngine"
Cohesion: 0.25
Nodes (7): _fade_edges(), ndarray, Path, Small wrapper around mlx-audio's Qwen3-TTS model., Short fades prevent clicks when independently generated chunks are joined., Generate mono float32 audio for one text chunk., TTSEngine

### Community 13 - "model_voices"
Cohesion: 0.38
Nodes (6): _list_voices(), model_voices(), Read preset speakers/languages from a Qwen3-TTS config without loading weights., _local_model(), test_cli_list_voices(), test_model_voices_reads_local_config()

## Knowledge Gaps
- **7 isolated node(s):** `qwen-book`, `Install`, `Quick start`, `Useful options`, `What it does` (+2 more)
  These have ≤1 connection - possible missing edges or undocumented components.
- **2 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `read_book()` connect `epub.py` to `cli.py`, `pipeline.py`, `text.py`, `m4b.py`?**
  _High betweenness centrality (0.076) - this node is a cross-community bridge._
- **Why does `_run()` connect `cli.py` to `epub.py`, `pipeline.py`, `main`, `load_ref_text`, `model_voices`?**
  _High betweenness centrality (0.061) - this node is a cross-community bridge._
- **Why does `run_calibration()` connect `pipeline.py` to `cli.py`, `compute_calibration`, `m4b.py`?**
  _High betweenness centrality (0.058) - this node is a cross-community bridge._
- **Are the 5 inferred relationships involving `AudioPart` (e.g. with `WavInfo` and `CalibrationMetrics`) actually correct?**
  _`AudioPart` has 5 INFERRED edges - model-reasoned connections that need verification._
- **What connects `qwen-book`, `Install`, `Quick start` to the rest of the system?**
  _7 weakly-connected nodes found - possible documentation gaps or missing edges._
- **Should `text.py` be split into smaller, more focused modules?**
  _Cohesion score 0.13043478260869565 - nodes in this community are weakly interconnected._