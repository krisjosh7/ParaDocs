from __future__ import annotations

import logging
from typing import Any

from context_catalog import context_library_paths
from schemas import StoreDocumentRequest

from .document_extract import extract_text_from_docx, extract_text_from_pdf
from .router import store_document_for_rag

logger = logging.getLogger(__name__)


def build_raw_text_for_context_rag(case_id: str, row: dict[str, Any]) -> str:
    """Produce text to send through the same /store pipeline for Research + semantic RAG."""
    cid = str(row.get("id", ""))
    title = str(row.get("title", "Untitled")).strip()
    caption = str(row.get("caption", "") or "").strip()
    ctype = str(row.get("type", ""))

    header = f"[Discovery context | case_id={case_id} | context_id={cid}]\nTitle: {title}\n"
    if caption:
        header += f"Caption: {caption}\n"
    header += "\n"

    if ctype == "text":
        body = str(row.get("text_full") or "").strip()
        if not body:
            return ""
        return header + body

    stored = row.get("stored_file")
    if not stored:
        return ""

    paths = context_library_paths(case_id)
    fp = paths["files"] / str(stored)
    if not fp.is_file():
        return header + f"(File missing on disk: {stored})"

    suffix = fp.suffix.lower()
    if suffix in (".txt", ".md", ".csv", ".json", ".xml", ".yml", ".yaml"):
        try:
            text = fp.read_text(encoding="utf-8", errors="replace").strip()
            if text:
                return header + text
        except OSError as e:
            logger.warning("Could not read text file for RAG: %s", e)

    if suffix == ".pdf":
        extracted = extract_text_from_pdf(fp)
        block = _pdf_docx_body_block(caption, extracted, "PDF")
        return header + block

    if suffix == ".docx":
        extracted = extract_text_from_docx(fp)
        block = _pdf_docx_body_block(caption, extracted, "DOCX")
        return header + block

    return (
        header
        + f"Type: {ctype}\n"
        + f"Original file name: {row.get('file_name') or fp.name}\n"
        + "(Binary or non-text format — no full-text extraction in this pass. "
        "Title and caption above are still indexed.)"
    )


def _pdf_docx_body_block(caption: str, extracted: str, label: str) -> str:
    """Caption is already in the header; here we add extracted body (plus optional caption repeat for RAG)."""
    parts: list[str] = []
    if caption:
        parts.append(f"Caption ({label}, repeated for retrieval):\n{caption}\n")
    parts.append(f"--- Extracted {label} text ---\n")
    if extracted.strip():
        parts.append(extracted.strip())
    else:
        parts.append(f"(No text could be extracted from this {label} file.)")
    return "\n".join(parts) + "\n"


def background_ingest_context_to_rag(case_id: str, row: dict[str, Any]) -> None:
    """Runs after HTTP response; failures are logged only."""
    try:
        raw = build_raw_text_for_context_rag(case_id, row)
        if not raw.strip():
            return
        payload = StoreDocumentRequest(
            case_id=case_id,
            raw_text=raw,
            source="upload",
            timestamp=None,
        )
        store_document_for_rag(payload)
    except Exception:
        logger.exception("Background RAG ingest failed for context %s", row.get("id"))
