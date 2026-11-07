from __future__ import annotations

import numpy as np
import pytest

from qwen_book.audio import write_wav
from qwen_book.epub import read_book
from qwen_book.m4b import AudioPart, ChapterMark, build_m4b, probe_m4b
from qwen_book.pipeline import make_plan


def test_make_plan_preview_budget(sample_epub):
    book = read_book(sample_epub)
    plans = make_plan(book, preview_chars=100, max_chars=80, min_chars=30)

    assert plans
    first_chapter_chars = sum(len(c.text) for c in plans[0].chunks)
    # The first chunk may overshoot the budget, but we should not include the whole book.
    assert first_chapter_chars < book.char_count


def test_make_plan_chapter_range(sample_epub):
    book = read_book(sample_epub)
    plans = make_plan(book, chapter_range=(2, 2))
    assert len(plans) == 1
    assert plans[0].chapter.title == "Part A"


def test_build_m4b_with_chapters_and_cover(tmp_path, sample_epub):
    book = read_book(sample_epub)
    sr = 24000

    one = tmp_path / "one.wav"
    two = tmp_path / "two.wav"
    info_one = write_wav(one, np.zeros(sr, dtype=np.float32), sr)
    info_two = write_wav(two, np.full(sr // 2, 0.01, dtype=np.float32), sr)

    chapters = [
        ChapterMark("Chapter One", 0, info_one.frames),
        ChapterMark("Chapter Two", info_one.frames, info_one.frames + info_two.frames),
    ]
    output = tmp_path / "book.m4b"
    cover = (book.cover.data, book.cover.media_type) if book.cover else None

    result = build_m4b(
        [AudioPart(one, info_one), AudioPart(two, info_two)],
        chapters,
        output,
        title=book.title,
        author=book.author,
        cover=cover,
        bitrate="64k",
    )

    assert result == output
    assert output.stat().st_size > 0

    info = probe_m4b(output)
    if info:
        assert len(info["chapters"]) == 2
        assert any(s["codec_name"] == "aac" for s in info["streams"])
        assert any((s.get("disposition") or {}).get("attached_pic") for s in info["streams"])
        assert abs(float(info["format"]["duration"]) - 1.5) < 0.2


@pytest.mark.parametrize(
    "start,end",
    [(0, 1), (1, 2), (1, 0)],
)
def test_chapter_validation_rejects_bad_marks(tmp_path, start, end):
    sr = 100
    path = tmp_path / "a.wav"
    info = write_wav(path, np.zeros(200, dtype=np.float32), sr)
    with pytest.raises(ValueError):
        build_m4b(
            [AudioPart(path, info)],
            [ChapterMark("bad", start, end)],
            tmp_path / "bad.m4b",
            title="T",
            author="A",
        )
