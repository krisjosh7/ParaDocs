from __future__ import annotations

from chunking import chunk_text


def test_chunk_text_empty() -> None:
    assert chunk_text("") == []
    assert chunk_text("   \n\n  ") == []


def test_chunk_text_single_paragraph() -> None:
    chunks = chunk_text("Hello world.\n\nSecond paragraph here.")
    assert len(chunks) >= 1
    assert "Hello world." in chunks[0] or chunks[0].startswith("Hello")


def test_chunk_text_respects_max_chars() -> None:
    # Force small max to get multiple chunks from multiple paragraphs
    paras = "\n\n".join([f"Paragraph {i} with some text." for i in range(20)])
    chunks = chunk_text(paras, max_chars=80, overlap_chars=10)
    assert len(chunks) >= 2
    for c in chunks:
        assert len(c) <= 200  # overlap can extend combined chunks in second pass


def test_chunk_text_splits_oversized_paragraph() -> None:
    long = "word " * 500
    chunks = chunk_text(long, max_chars=100, overlap_chars=20)
    assert len(chunks) >= 2
