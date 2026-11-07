"""Text normalization and chunking for TTS."""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .epub import Block

_WS_RE = re.compile(r"\s+")
_CONTROL_RE = re.compile(r"[\u0000-\u0008\u000b\u000c\u000e-\u001f\u007f]")
_SENTENCE_RE = re.compile(r"(?<=[.!?…。！？])\s+")
_CLAUSE_RE = re.compile(r"(?<=[;:,])\s+")
_ZERO_WIDTH = dict.fromkeys(map(ord, "\u200b\u200c\u200d\ufeff"), None)

_QWEN_LANGUAGES = {
    "auto",
    "chinese",
    "english",
    "german",
    "italian",
    "portuguese",
    "spanish",
    "japanese",
    "korean",
    "french",
    "russian",
}

_ISO_TO_QWEN = {
    "en": "english",
    "de": "german",
    "it": "italian",
    "pt": "portuguese",
    "es": "spanish",
    "ja": "japanese",
    "ko": "korean",
    "fr": "french",
    "ru": "russian",
    "zh": "chinese",
    "cn": "chinese",
    "cmn": "chinese",
}


@dataclass(frozen=True)
class SpeechChunk:
    text: str
    pause_after_ms: int = 250


def normalize_text(text: str) -> str:
    """Normalize whitespace and punctuation noise without changing meaning."""
    text = unicodedata.normalize("NFC", text)
    text = text.translate(_ZERO_WIDTH)
    text = text.replace("\u00ad", "").replace("\u00a0", " ")
    text = text.replace("\u2026", "...")
    text = _CONTROL_RE.sub(" ", text)
    text = _WS_RE.sub(" ", text)
    return text.strip()


def split_sentences(text: str) -> list[str]:
    """Split text at sentence-ending punctuation, keeping long sentences whole."""
    text = normalize_text(text)
    if not text:
        return []
    return [part.strip() for part in _SENTENCE_RE.split(text) if part.strip()]


def chunk_blocks(
    blocks: list[Block],
    *,
    max_chars: int = 280,
    min_chars: int = 90,
    pause_ms: int = 250,
    paragraph_pause_ms: int = 420,
    chapter_head_pause_ms: int = 700,
) -> list[SpeechChunk]:
    """Turn chapter blocks into TTS-sized chunks with natural pauses.

    Paragraphs and sentences are merged only while a chunk is below ``min_chars``.
    This avoids tiny unstable generations without making every call maximum-length.
    """
    if max_chars < 20:
        raise ValueError("max_chars must be at least 20")
    if min_chars > max_chars:
        raise ValueError("min_chars cannot exceed max_chars")

    units: list[tuple[str, int, bool]] = []
    for block in blocks:
        text = normalize_text(block.text)
        if not text:
            continue
        sentences = split_sentences(text)
        if not sentences:
            sentences = [text]
        expanded: list[str] = []
        for sentence in sentences:
            expanded.extend(_split_long(sentence, max_chars))
        for index, unit in enumerate(expanded):
            is_last = index == len(expanded) - 1
            if block.kind == "heading":
                pause = chapter_head_pause_ms if is_last else pause_ms
            else:
                pause = paragraph_pause_ms if is_last else pause_ms
            units.append((unit, pause, block.kind == "heading"))

    chunks: list[SpeechChunk] = []
    current = ""
    current_pause = pause_ms
    current_heading = False

    def flush() -> None:
        nonlocal current, current_pause, current_heading
        if current:
            chunks.append(SpeechChunk(text=current, pause_after_ms=current_pause))
        current = ""
        current_pause = pause_ms
        current_heading = False

    for text, pause, heading in units:
        if not current:
            current, current_pause, current_heading = text, pause, heading
            continue

        combined_len = len(current) + 1 + len(text)
        should_merge = (
            combined_len <= max_chars
            and not current_heading
            and not heading
            and (len(current) < min_chars or len(text) < min_chars)
        )
        if should_merge:
            current += " " + text
            current_pause = max(current_pause, pause)
        else:
            flush()
            current, current_pause, current_heading = text, pause, heading

    flush()
    return chunks


def limit_chunks(chunks: list[SpeechChunk], max_chars: int | None) -> list[SpeechChunk]:
    """Keep whole chunks without exceeding the character budget."""
    if not max_chars or max_chars <= 0:
        return chunks
    result: list[SpeechChunk] = []
    used = 0
    for chunk in chunks:
        if used + len(chunk.text) > max_chars:
            break
        result.append(chunk)
        used += len(chunk.text)
    if not result and chunks:
        result.append(chunks[0])
    return result


def language_to_qwen(code: str | None) -> str:
    """Map an EPUB/ISO language code to a Qwen3-TTS language name."""
    if not code:
        return "auto"
    value = code.strip().lower().replace("_", "-")
    if value in _QWEN_LANGUAGES:
        return value
    primary = value.split("-", 1)[0]
    if primary in _QWEN_LANGUAGES:
        return primary
    return _ISO_TO_QWEN.get(primary, "auto")


def _split_long(text: str, max_chars: int) -> list[str]:
    if len(text) <= max_chars:
        return [text]

    pieces: list[str] = []
    for clause in _CLAUSE_RE.split(text):
        clause = clause.strip()
        if not clause:
            continue
        if len(clause) <= max_chars:
            pieces.append(clause)
            continue
        pieces.extend(_split_by_words(clause, max_chars))
    return _merge_pieces(pieces, max_chars) if pieces else _split_by_words(text, max_chars)


def _split_by_words(text: str, max_chars: int) -> list[str]:
    words = text.split()
    if not words:
        return [text[index : index + max_chars] for index in range(0, len(text), max_chars)]

    pieces: list[str] = []
    current = ""
    for word in words:
        if len(word) > max_chars:
            if current:
                pieces.append(current)
                current = ""
            pieces.extend(word[index : index + max_chars] for index in range(0, len(word), max_chars))
            continue
        candidate = f"{current} {word}".strip()
        if len(candidate) <= max_chars:
            current = candidate
        else:
            if current:
                pieces.append(current)
            current = word
    if current:
        pieces.append(current)
    return pieces


def _merge_pieces(pieces: list[str], max_chars: int) -> list[str]:
    merged: list[str] = []
    current = ""
    for piece in pieces:
        candidate = f"{current} {piece}".strip()
        if current and len(candidate) <= max_chars:
            current = candidate
        else:
            if current:
                merged.append(current)
            current = piece
    if current:
        merged.append(current)
    return merged
