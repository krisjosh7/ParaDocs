from __future__ import annotations


def _paragraphs(raw_text: str) -> list[str]:
    paras = [p.strip() for p in raw_text.split("\n\n")]
    return [p for p in paras if p]


def chunk_text(raw_text: str, max_chars: int = 3800, overlap_chars: int = 450) -> list[str]:
    """
    Approximate 500-1000 token chunks with ~100 token overlap.
    Uses characters for deterministic chunk sizing.
    """
    paragraphs = _paragraphs(raw_text)
    if not paragraphs:
        return []

    chunks: list[str] = []
    current: list[str] = []
    current_len = 0

    def flush() -> None:
        nonlocal current, current_len
        if current:
            chunks.append("\n\n".join(current).strip())
            current = []
            current_len = 0

    for para in paragraphs:
        para_len = len(para)
        if para_len > max_chars:
            flush()
            start = 0
            while start < para_len:
                end = min(start + max_chars, para_len)
                piece = para[start:end].strip()
                if piece:
                    chunks.append(piece)
                if end >= para_len:
                    break
                start = max(0, end - overlap_chars)
            continue

        projected = current_len + para_len + (2 if current else 0)
        if projected <= max_chars:
            current.append(para)
            current_len = projected
            continue

        flush()
        current.append(para)
        current_len = para_len

    flush()
    if len(chunks) <= 1:
        return chunks

    with_overlap: list[str] = []
    for idx, chunk in enumerate(chunks):
        if idx == 0:
            with_overlap.append(chunk)
            continue
        prev_tail = chunks[idx - 1][-overlap_chars:]
        with_overlap.append((prev_tail + "\n\n" + chunk).strip())
    return with_overlap
