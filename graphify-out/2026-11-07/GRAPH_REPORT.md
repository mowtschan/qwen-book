# Graph Report - qwen-book  (2026-11-07)

## Corpus Check
- 19 files · ~7,639 words
- Verdict: corpus is large enough that graph structure adds value.

## Summary
- 169 nodes · 404 edges · 10 communities (8 shown, 2 thin omitted)
- Extraction: 94% EXTRACTED · 6% INFERRED · 0% AMBIGUOUS · INFERRED: 23 edges (avg confidence: 0.5)
- Token cost: 0 input · 0 output

## Community Hubs (Navigation)
- cli.py
- epub.py
- pipeline.py
- text.py
- m4b.py
- qwen-book
- sample_epub
- __init__.py
- qwen-book
- compute_calibration

## God Nodes (most connected - your core abstractions)
1. `_run()` - 19 edges
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
- `test_cli_calibrate_requires_dry_run()` --calls--> `main()`  [EXTRACTED]
  tests/test_cli.py → src/qwen_book/cli.py
- `test_cli_dry_run()` --calls--> `main()`  [EXTRACTED]
  tests/test_cli.py → src/qwen_book/cli.py
- `test_cli_rejects_bad_chapter_range()` --calls--> `main()`  [EXTRACTED]
  tests/test_cli.py → src/qwen_book/cli.py
- `test_chunk_blocks_keeps_limits_and_heading_pause()` --calls--> `Block`  [EXTRACTED]
  tests/test_text.py → src/qwen_book/epub.py
- `test_chunk_blocks_merges_tiny_paragraphs()` --calls--> `Block`  [EXTRACTED]
  tests/test_text.py → src/qwen_book/epub.py

## Import Cycles
- None detected.

## Communities (10 total, 2 thin omitted)

### Community 0 - "cli.py"
Cohesion: 0.09
Nodes (34): ArgumentParser, Namespace, build_parser(), _chars_per_second(), _default_work_dir(), _human_duration(), _list_voices(), _load_tts() (+26 more)

### Community 1 - "epub.py"
Cohesion: 0.17
Nodes (24): _add_toc(), Block, _chapter_title(), _clean_inline(), Cover, extract_blocks(), _find_cover(), _find_item_by_href() (+16 more)

### Community 2 - "pipeline.py"
Cohesion: 0.15
Nodes (31): read_wav_info(), Book, Chapter, AudioPart, wav_part(), CalibrationMetrics, ChapterPlan, _chunk_key() (+23 more)

### Community 3 - "text.py"
Cohesion: 0.18
Nodes (16): chunk_blocks(), language_to_qwen(), _merge_pieces(), normalize_text(), Text normalization and chunking for TTS., Map an EPUB/ISO language code to a Qwen3-TTS language name., Normalize whitespace and punctuation noise without changing meaning., Split text at sentence-ending punctuation, keeping long sentences whole. (+8 more)

### Community 4 - "m4b.py"
Cohesion: 0.16
Nodes (23): parametrize, ndarray, Path, Minimal WAV helpers using only the standard library., _to_pcm16(), WavInfo, write_silence(), write_wav() (+15 more)

### Community 6 - "qwen-book"
Cohesion: 0.25
Nodes (7): Install, Notes, Output and cache, Quick start, qwen-book, Useful options, What it does

### Community 7 - "sample_epub"
Cohesion: 0.50
Nodes (3): fixture, Path, sample_epub()

### Community 10 - "compute_calibration"
Cohesion: 0.43
Nodes (6): compute_calibration(), Measure speech rate and steady-state synthesis RTF from real chunks., test_compute_calibration_drops_first_chunk_warmup(), test_compute_calibration_keeps_normal_first_chunk(), test_compute_calibration_rejects_empty(), test_estimate_range_adds_pauses_and_warmup()

## Knowledge Gaps
- **7 isolated node(s):** `qwen-book`, `Install`, `Quick start`, `Useful options`, `What it does` (+2 more)
  These have ≤1 connection - possible missing edges or undocumented components.
- **2 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `read_book()` connect `epub.py` to `cli.py`, `pipeline.py`, `text.py`, `m4b.py`?**
  _High betweenness centrality (0.076) - this node is a cross-community bridge._
- **Why does `run_calibration()` connect `pipeline.py` to `cli.py`, `compute_calibration`, `m4b.py`?**
  _High betweenness centrality (0.056) - this node is a cross-community bridge._
- **Why does `_run()` connect `cli.py` to `epub.py`, `pipeline.py`, `text.py`?**
  _High betweenness centrality (0.049) - this node is a cross-community bridge._
- **Are the 5 inferred relationships involving `AudioPart` (e.g. with `WavInfo` and `CalibrationMetrics`) actually correct?**
  _`AudioPart` has 5 INFERRED edges - model-reasoned connections that need verification._
- **What connects `qwen-book`, `Install`, `Quick start` to the rest of the system?**
  _7 weakly-connected nodes found - possible documentation gaps or missing edges._
- **Should `cli.py` be split into smaller, more focused modules?**
  _Cohesion score 0.09390243902439024 - nodes in this community are weakly interconnected._