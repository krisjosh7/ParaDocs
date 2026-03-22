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
from elevenlabs_stt import transcribe_audio_for_ingest
from groq_llm import describe_image_for_ingest
from schemas import StoreDocumentRequest
from storage import ensure_case_dirs

from .document_extract import (
    extract_text_from_docx,
    extract_text_from_pdf,
    is_audio_suffix,
    is_image_suffix,
)
from .router import store_document_for_rag

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

    if is_image_suffix(suffix):
        visual = describe_image_for_ingest(fp, caption=caption)
        block = _image_rag_body_block(caption, visual)
        return header + block

    if is_audio_suffix(suffix):
        transcript = transcribe_audio_for_ingest(fp)
        block = _audio_rag_body_block(caption, transcript)
        return header + block

    return (
        header
        + f"Type: {ctype}\n"
        + f"Original file name: {row.get('file_name') or fp.name}\n"
        + "(Binary or non-text format — no full-text extraction in this pass. "
        "Title and caption above are still indexed.)"
    )


def _audio_rag_body_block(caption: str, transcript: str) -> str:
    """Combine optional caption with ElevenLabs transcript for embedding."""
    parts: list[str] = []
    if caption:
        parts.append(
            "User-provided caption (for retrieval; aligns with the transcript below):\n"
            f"{caption}\n",
        )
    parts.append("--- Transcript (ElevenLabs speech-to-text) ---\n")
    if transcript.strip():
        parts.append(transcript.strip())
    else:
        parts.append(
            "(No transcript was returned—set ELEVENLABS_API_KEY, check plan/access, or verify file format.)",
        )
    return "\n".join(parts) + "\n"


def _image_rag_body_block(caption: str, visual_description: str) -> str:
    """Combine optional caption with vision-model text for embedding (caption is also in header)."""
    parts: list[str] = []
    if caption:
        parts.append(
            "User-provided caption (for retrieval; cross-check with the visual description below):\n"
            f"{caption}\n",
        )
    parts.append("--- Visual description (from image analysis) ---\n")
    if visual_description.strip():
        parts.append(visual_description.strip())
    else:
        parts.append(
            "(No visual description was generated—check GROQ_API_KEY, model access, or image size/format.)",
        )
    return "\n".join(parts) + "\n"


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
        try:
            from workflow.reasoning_agent import enqueue_reasoning_job

            enqueue_reasoning_job(case_id, "post_ingest", priority=1, force=False)
        except Exception:
            logger.exception("Failed to enqueue reasoning job after ingest for case_id=%s", case_id)
    except Exception as exc:
        logger.exception("Background RAG ingest failed for context %s", row.get("id"))
        if ctx_id:
            set_rag_ingest_failed(case_id, ctx_id, _format_ingest_error(exc))
