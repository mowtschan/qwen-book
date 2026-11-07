from __future__ import annotations

from qwen_book.epub import extract_blocks, read_book


def test_read_book_metadata_and_chapters(sample_epub):
    book = read_book(sample_epub)

    assert book.title == "Test Book"
    assert book.author == "Ada Author"
    assert book.language_code == "en"
    assert book.language == "english"
    assert book.cover is not None
    assert book.cover.media_type == "image/png"
    assert [chapter.title for chapter in book.chapters] == [
        "Chapter One",
        "Part A",
        "Part B",
    ]

    first = book.chapters[0]
    text = " ".join(block.text for block in first.blocks)
    assert "first paragraph" in text
    assert "Quoted text should appear only once" in text
    assert "ignore this script" not in text
    # Footnote reference marker is removed.
    assert "footnote1" not in text


def test_extract_blocks_does_not_duplicate_nested_paragraphs():
    html = """
    <html><body>
      <blockquote><p>Only once.</p></blockquote>
      <p>A normal paragraph.</p>
    </body></html>
    """
    blocks = extract_blocks(html)
    texts = [block.text for block in blocks]
    assert texts == ["Only once.", "A normal paragraph."]
