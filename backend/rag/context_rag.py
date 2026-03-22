from __future__ import annotations

import asyncio
import logging
from typing import Any

from context_catalog import (
    context_library_paths,
    set_rag_doc_id_for_context,
    set_rag_ingest_failed,
)
from storage import ensure_case_dirs

from .document_extract import extract_text_from_docx, extract_text_from_pdf

logger = logging.getLogger(__name__)


def build_raw_text_for_context_rag(case_id: str, row: dict[str, Any]) -> str:
    """Produce text to send through the same /store pipeline for context library RAG ingest."""
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


def _format_ingest_error(exc: Exception) -> str:
    """Human-readable message for catalog + logs (includes FastAPI HTTPException detail)."""
    detail = getattr(exc, "detail", None)
    if isinstance(detail, str) and detail.strip():
        return detail.strip()
    return f"{type(exc).__name__}: {exc}"


def background_ingest_context_to_rag(case_id: str, row: dict[str, Any]) -> None:
    """Runs after HTTP response: full case LangGraph (ingest → events → timeline → research), then links catalog row to doc_id."""
    ctx_id = str(row.get("id") or "")
    try:
        raw = build_raw_text_for_context_rag(case_id, row)
        if not raw.strip():
            return
        ensure_case_dirs(case_id)
        from workflow import initial_case_state, run_case_workflow

        final = asyncio.run(
            run_case_workflow(initial_case_state(case_id, raw, "upload", context_id=ctx_id)),
        )
        docs = final.get("documents") or []
        doc_id = str((docs[-1] or {}).get("doc_id") or "").strip()
        if ctx_id and doc_id:
            set_rag_doc_id_for_context(case_id, ctx_id, doc_id)
    except Exception as exc:
        logger.exception("Background RAG ingest failed for context %s", row.get("id"))
        if ctx_id:
            set_rag_ingest_failed(case_id, ctx_id, _format_ingest_error(exc))
