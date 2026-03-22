from __future__ import annotations

import logging
from pathlib import Path

try:
    from pypdf import PdfReader
except ImportError:
    PdfReader = None  # type: ignore[misc, assignment]

try:
    from docx import Document as DocxDocument
except ImportError:
    DocxDocument = None  # type: ignore[misc, assignment]

logger = logging.getLogger(__name__)


def extract_text_from_pdf(path: Path) -> str:
    """Extract plain text from a PDF file. Returns empty string on failure."""
    if PdfReader is None:
        logger.warning("pypdf not installed; cannot extract PDF text")
        return ""

    try:
        reader = PdfReader(str(path))
        parts: list[str] = []
        for page in reader.pages:
            try:
                t = page.extract_text()
            except Exception:
                t = None
            if t and t.strip():
                parts.append(t.strip())
        return "\n\n".join(parts).strip()
    except Exception as e:
        logger.warning("PDF text extraction failed for %s: %s", path, e)
        return ""


def extract_text_from_docx(path: Path) -> str:
    """Extract plain text from a .docx file. Returns empty string on failure."""
    if DocxDocument is None:
        logger.warning("python-docx not installed; cannot extract DOCX text")
        return ""

    try:
        doc = DocxDocument(str(path))
        parts: list[str] = []
        for para in doc.paragraphs:
            if para.text and para.text.strip():
                parts.append(para.text.strip())
        for table in doc.tables:
            for row in table.rows:
                cells = [c.text.strip() for c in row.cells if c.text and c.text.strip()]
                if cells:
                    parts.append(" | ".join(cells))
        return "\n\n".join(parts).strip()
    except Exception as e:
        logger.warning("DOCX text extraction failed for %s: %s", path, e)
        return ""
