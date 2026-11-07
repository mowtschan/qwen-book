from __future__ import annotations

from qwen_book.epub import Block
from qwen_book.text import (
    SpeechChunk,
    chunk_blocks,
    language_to_qwen,
    limit_chunks,
    normalize_text,
)


def test_normalize_text():
    assert normalize_text("hello\u00ad  world\u2026\u00a0again") == "hello world... again"


def test_language_mapping():
    assert language_to_qwen("en") == "english"
    assert language_to_qwen("ru-RU") == "russian"
    assert language_to_qwen("English") == "english"
    assert language_to_qwen("xx") == "auto"
    assert language_to_qwen(None) == "auto"


def test_chunk_blocks_keeps_limits_and_heading_pause():
    paragraph = "This is a sentence. " * 40
    blocks = [
        Block(kind="heading", text="Chapter One", level=1),
        Block(kind="text", text=paragraph.strip()),
    ]
    chunks = chunk_blocks(blocks, max_chars=120, min_chars=40)

    assert chunks[0].text == "Chapter One"
    assert chunks[0].pause_after_ms == 700
    assert all(len(chunk.text) <= 120 for chunk in chunks)
    assert all(chunk.pause_after_ms > 0 for chunk in chunks)


def test_chunk_blocks_merges_tiny_paragraphs():
    blocks = [
        Block(kind="text", text="Short one."),
        Block(kind="text", text="Short two."),
    ]
    chunks = chunk_blocks(blocks, max_chars=100, min_chars=50)
    assert len(chunks) == 1
    assert chunks[0].text == "Short one. Short two."


def test_limit_chunks_keeps_whole_chunks():
    chunks = [SpeechChunk("a" * 10), SpeechChunk("b" * 10), SpeechChunk("c" * 10)]
    assert len(limit_chunks(chunks, 15)) == 1
    assert limit_chunks(chunks, 0) == chunks
