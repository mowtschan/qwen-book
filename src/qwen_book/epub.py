"""EPUB reading and chapter extraction."""

from __future__ import annotations

import mimetypes
import re
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

import ebooklib
from bs4 import BeautifulSoup
from ebooklib import epub
from ebooklib.toc import Link, Section

from .text import language_to_qwen

BLOCK_TAGS = {
    "h1",
    "h2",
    "h3",
    "h4",
    "h5",
    "h6",
    "p",
    "li",
    "blockquote",
    "pre",
    "figcaption",
    "dt",
    "dd",
    "td",
}
HEADING_TAGS = {f"h{level}" for level in range(1, 7)}
DROP_TAGS = ("script", "style", "nav", "svg", "audio", "video", "iframe", "noscript")
_WS_RE = re.compile(r"\s+")


@dataclass(frozen=True)
class Block:
    kind: str
    text: str
    level: int = 0


@dataclass
class Chapter:
    index: int
    title: str
    href: str
    blocks: list[Block] = field(default_factory=list)

    @property
    def char_count(self) -> int:
        return sum(len(block.text) for block in self.blocks)


@dataclass
class Cover:
    data: bytes
    media_type: str
    file_name: str


@dataclass
class Book:
    path: Path
    title: str
    author: str
    language_code: str
    language: str
    chapters: list[Chapter]
    cover: Cover | None = None

    @property
    def char_count(self) -> int:
        return sum(chapter.char_count for chapter in self.chapters)


def read_book(path: str | Path) -> Book:
    """Read an EPUB and return ordered chapters with clean text blocks."""
    path = Path(path)
    if not path.is_file():
        raise FileNotFoundError(f"EPUB not found: {path}")
    if path.suffix.lower() != ".epub":
        raise ValueError(f"Not an EPUB file: {path}")

    raw = epub.read_epub(str(path))
    title = _first_metadata(raw, "title") or path.stem
    author = ", ".join(_unique(_metadata_values(raw, "creator"))) or "Unknown"
    language_code = (_first_metadata(raw, "language") or raw.language or "").strip()
    toc_titles = _toc_title_map(raw.toc)
    chapters: list[Chapter] = []

    for idref, linear in raw.spine:
        if str(linear).lower() == "no":
            continue
        item = raw.get_item_with_id(idref)
        if item is None or item.get_type() != ebooklib.ITEM_DOCUMENT:
            continue
        is_chapter = getattr(item, "is_chapter", None)
        if callable(is_chapter) and not is_chapter():
            continue

        blocks = extract_blocks(item.get_content())
        if not blocks:
            continue

        href = item.file_name or idref
        fallback_title = (
            toc_titles.get(_href_key(href))
            or toc_titles.get(Path(href).name)
            or getattr(item, "title", "")
            or f"Chapter {len(chapters) + 1}"
        )
        for chapter in _split_blocks(
            blocks, fallback_title=fallback_title, href=href, book_title=title
        ):
            chapter.index = len(chapters) + 1
            chapters.append(chapter)

    if not chapters:
        raise ValueError(f"No readable chapters found in {path}")

    return Book(
        path=path,
        title=title,
        author=author,
        language_code=language_code,
        language=language_to_qwen(language_code),
        chapters=chapters,
        cover=_find_cover(raw),
    )


def extract_blocks(html: bytes | str) -> list[Block]:
    """Extract heading/paragraph-like blocks from an EPUB XHTML document."""
    soup = BeautifulSoup(html, "html.parser")
    body = soup.body or soup

    for tag in body.find_all(DROP_TAGS):
        tag.decompose()

    # Strip common footnote reference markers such as <sup><a>1</a></sup>.
    for tag in body.find_all("sup"):
        text = tag.get_text(" ", strip=True)
        if tag.find("a") or re.fullmatch(r"[\d\s.,-]+", text):
            tag.decompose()

    blocks: list[Block] = []
    for element in body.find_all(BLOCK_TAGS):
        if element.find_parent(BLOCK_TAGS):
            continue
        text = _clean_inline(element.get_text(" ", strip=True))
        if not _meaningful(text, heading=element.name in HEADING_TAGS):
            continue
        level = int(element.name[1]) if element.name in HEADING_TAGS else 0
        kind = "heading" if level else "text"
        block = Block(kind=kind, text=text, level=level)
        if blocks and blocks[-1] == block:
            continue
        blocks.append(block)

    if blocks:
        return blocks

    # Broken books sometimes put the whole section in bare text nodes. Keep it usable.
    text = _clean_inline(body.get_text("\n", strip=True))
    if not _meaningful(text, heading=False):
        return []
    return [
        Block(kind="text", text=_clean_inline(line))
        for line in re.split(r"\n+", text)
        if _meaningful(line, heading=False)
    ]


def _split_blocks(
    blocks: list[Block], fallback_title: str, href: str, book_title: str = ""
) -> list[Chapter]:
    # Some EPUBs put the book title in every chapter file before the real heading.
    if blocks and _same_title(blocks[0].text, book_title) and blocks[0].kind == "heading":
        blocks = blocks[1:]
        if not blocks:
            return []

    heading_counts = Counter(block.level for block in blocks if block.kind == "heading")
    split_level = next((level for level in (1, 2) if heading_counts[level] >= 2), None)
    if split_level is None:
        title = _chapter_title(blocks, fallback_title, book_title=book_title)
        return [Chapter(index=0, title=title, href=href, blocks=blocks)]

    chapters: list[Chapter] = []
    current: list[Block] = []
    current_title = fallback_title

    def flush() -> None:
        nonlocal current, current_title
        if not current:
            return
        title = _chapter_title(current, current_title, book_title=book_title)
        chapters.append(Chapter(index=0, title=title, href=href, blocks=current))
        current = []

    for block in blocks:
        starts_chapter = block.kind == "heading" and 0 < block.level <= split_level
        if starts_chapter and current:
            flush()
        if starts_chapter:
            current_title = block.text
        current.append(block)

    flush()
    return chapters


def _chapter_title(blocks: list[Block], fallback: str, *, book_title: str = "") -> str:
    for block in blocks:
        if block.kind == "heading" and not _same_title(block.text, book_title):
            return _short_title(block.text)
    return _short_title(fallback or "Untitled chapter")


def _same_title(left: str, right: str) -> bool:
    if not left or not right:
        return False
    return _clean_inline(left).casefold() == _clean_inline(right).casefold()


def _short_title(value: str, limit: int = 120) -> str:
    value = _clean_inline(value)
    if len(value) <= limit:
        return value
    return value[: limit - 1].rstrip() + "…"


def _clean_inline(value: str) -> str:
    value = value.replace("\u00a0", " ").replace("\u00ad", "")
    return _WS_RE.sub(" ", value).strip()


def _meaningful(text: str, *, heading: bool) -> bool:
    if not text:
        return False
    if heading:
        return any(char.isalnum() for char in text)
    return len(text) >= 2 and any(char.isalnum() for char in text)


def _metadata_values(book, name: str) -> list[str]:
    values: list[str] = []
    for entry in book.get_metadata("DC", name):
        value = entry[0] if isinstance(entry, tuple) else entry
        if value and str(value).strip():
            values.append(str(value).strip())
    return values


def _first_metadata(book, name: str) -> str:
    values = _metadata_values(book, name)
    return values[0] if values else ""


def _unique(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        if value not in seen:
            seen.add(value)
            result.append(value)
    return result


def _toc_title_map(toc) -> dict[str, str]:
    result: dict[str, str] = {}

    def visit(items) -> None:
        for item in items:
            if isinstance(item, tuple):
                section, children = item
                if isinstance(section, Section) and section.title:
                    _add_toc(result, section.href, section.title)
                visit(children)
            elif isinstance(item, Link):
                _add_toc(result, item.href, item.title)

    visit(toc)
    return result


def _add_toc(result: dict[str, str], href: str, title: str) -> None:
    if href and title:
        result.setdefault(_href_key(href), _clean_inline(title))
        result.setdefault(Path(_href_key(href)).name, _clean_inline(title))


def _href_key(href: str) -> str:
    return (href or "").split("#", 1)[0]


def _find_cover(book) -> Cover | None:
    candidates = list(book.get_items_of_type(ebooklib.ITEM_COVER))

    if not candidates:
        # EPUB2: <meta name="cover" content="image-item-id"/>.
        for namespace in book.metadata.values():
            for entries in namespace.values():
                for entry in entries:
                    if not isinstance(entry, tuple):
                        continue
                    _, attrs = entry
                    if not isinstance(attrs, dict) or attrs.get("name") != "cover":
                        continue
                    item = book.get_item_with_id(str(attrs.get("content") or ""))
                    if item is not None and (item.media_type or "").startswith("image/"):
                        candidates.append(item)

    if not candidates:
        # EPUB2 guide: <reference type="cover" href="..."/>.
        for reference in getattr(book, "guide", []) or []:
            if str(reference.get("type", "")).lower() != "cover":
                continue
            href = reference.get("href")
            item = _find_item_by_href(book, href) if href else None
            if item is not None and (item.media_type or "").startswith("image/"):
                candidates.append(item)

    if not candidates:
        for entry in book.get_metadata("OPF", "cover"):
            value = entry[0] if isinstance(entry, tuple) else entry
            item = book.get_item_with_id(str(value)) if value else None
            if item is not None and (item.media_type or "").startswith("image/"):
                candidates.append(item)

    if not candidates:
        candidates = [
            item
            for item in book.get_items_of_type(ebooklib.ITEM_IMAGE)
            if "cover" in (item.file_name or "").lower()
        ]

    for item in candidates:
        data = item.get_content()
        if not data:
            continue
        media_type = item.media_type or mimetypes.guess_type(item.file_name or "")[0]
        if not media_type or not media_type.startswith("image/"):
            continue
        if media_type.lower() == "image/svg+xml":
            # MP4 cover art must be a raster image.
            continue
        return Cover(
            data=data,
            media_type=media_type,
            file_name=Path(item.file_name or "cover.jpg").name,
        )
    return None


def _find_item_by_href(book, href: str):
    target = _href_key(href)
    target_name = Path(target).name
    for item in book.get_items():
        file_name = item.file_name or ""
        if file_name == target or Path(file_name).name == target_name:
            return item
    return None
