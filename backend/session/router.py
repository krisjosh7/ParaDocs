import asyncio
import os
import tempfile
import uuid
from typing import Optional

import httpx
import whisper
from fastapi import APIRouter, HTTPException, UploadFile, File
from pydantic import BaseModel

from research.courtlistener import search_opinions
from rag.router import store_document_for_rag
from schemas import StoreDocumentRequest

router = APIRouter(prefix="/session", tags=["session"])

RAG_BASE = os.environ.get("RAG_BASE_URL", "http://localhost:8000")

# Don't bother querying for one-word answers like "Yes" or "Okay"
MIN_TEXT_LENGTH = 20

# Spoken filler words that add no signal to a legal search query
_FILLERS = {
    "um", "uh", "like", "you know", "i mean", "so", "well", "actually",
    "basically", "right", "okay", "yeah", "yes", "no", "good", "great",
    "sure", "i", "my", "we", "they", "it", "the", "a", "an", "and",
    "but", "or", "just", "really", "very", "kind of", "sort of",
}


def _clean_query(text: str) -> str:
    """Strip filler words and short tokens to leave substantive legal terms."""
    words = text.lower().split()
    kept = [w.strip(".,?!;:\"'") for w in words if w.strip(".,?!;:\"'") not in _FILLERS]
    meaningful = [w for w in kept if len(w) > 2]
    return " ".join(meaningful)


def _build_search_query(text: str, context: list[str]) -> str:
    """
    Combine the last context lines with the current text, clean filler words.
    Using context gives CourtListener more signal than a single spoken sentence.
    """
    combined = " ".join(context[-2:] + [text])
    return _clean_query(combined)

# Load once at startup — takes ~5s for "base", stays in memory for the session
_whisper_model = whisper.load_model("base")


# ---------------------------------------------------------------------------
# Request / Response models
# ---------------------------------------------------------------------------

class SessionQueryRequest(BaseModel):
    case_id: str
    text: str              # the latest transcript line
    line_index: int        # 0-based index in the transcript — echoed back in items
    context: list[str] = []  # last N transcript lines for richer search queries


class SurfacedItem(BaseModel):
    id: str
    after_line: int
    type: str            # "document" | "caselaw"
    status: str          # "hit"
    label: str
    excerpt: Optional[str]
    relevance: Optional[float]
    url: Optional[str]   # direct link to the source


class SessionQueryResponse(BaseModel):
    items: list[SurfacedItem]


class SaveToContextRequest(BaseModel):
    case_id: str
    label: str       # case name / title
    excerpt: str = ""  # snippet text
    url: str = ""      # source URL (e.g. CourtListener link)


# ---------------------------------------------------------------------------
# POST /session/transcribe
# ---------------------------------------------------------------------------

@router.post("/transcribe")
async def transcribe(audio: UploadFile = File(...)):
    """
    Accepts a raw audio blob from the browser's MediaRecorder, runs Whisper,
    and returns the transcribed text.

    model.transcribe() is CPU-bound so it runs in a thread pool to avoid
    blocking the async event loop.
    """
    suffix = ".webm"
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as f:
        f.write(await audio.read())
        tmp_path = f.name

    try:
        result = await asyncio.get_event_loop().run_in_executor(
            None, _whisper_model.transcribe, tmp_path
        )
    finally:
        os.unlink(tmp_path)

    text = result["text"].strip()

    # Filter out Whisper's noise/silence placeholders
    if text.lower() in {"", "[blank_audio]", "[music]", "[silence]"}:
        text = ""

    return {"text": text}


# ---------------------------------------------------------------------------
# POST /session/query
# ---------------------------------------------------------------------------

@router.post("/query", response_model=SessionQueryResponse)
async def session_query(req: SessionQueryRequest):
    """
    Called after each new transcript line arrives.
    Returns relevant documents from RAG and matching case law from CourtListener.

    Both calls run in parallel. Failures in either are swallowed so a slow
    or unreachable service never breaks the live session.
    """
    if len(req.text.strip()) < MIN_TEXT_LENGTH:
        return SessionQueryResponse(items=[])

    items: list[SurfacedItem] = []

    # ── 1. RAG document hits ─────────────────────────────────────────────────
    rag_items = await _query_rag(req.case_id, req.text, req.line_index)
    items.extend(rag_items)

    # ── 2. CourtListener case law ────────────────────────────────────────────
    case_items = await _query_courtlistener(req.text, req.context, req.line_index)
    items.extend(case_items)

    return SessionQueryResponse(items=items)


# ---------------------------------------------------------------------------
# POST /session/save-to-context
# ---------------------------------------------------------------------------

@router.post("/save-to-context")
async def save_to_context(req: SaveToContextRequest):
    """
    Saves a surfaced case snippet into the RAG store so it becomes searchable
    within the case's document context going forward.

    Calls store_document_for_rag directly instead of HTTP self-call to avoid
    deadlocking a single-worker uvicorn server.
    """
    import logging
    logger = logging.getLogger(__name__)

    # Build a rich text block so the stored document is self-contained
    parts = [req.label]
    if req.url:
        parts.append(f"Source: {req.url}")
    if req.excerpt:
        parts.append(f"\n{req.excerpt}")
    raw_text = "\n".join(parts)

    logger.info("save-to-context: case_id=%s, raw_text length=%d", req.case_id, len(raw_text))

    try:
        url_clean = (req.url or "").strip()
        result = store_document_for_rag(StoreDocumentRequest(
            case_id=req.case_id,
            raw_text=raw_text,
            source="web",
            source_url=url_clean if url_clean else None,
        ))
        logger.info("save-to-context: stored doc_id=%s, chunks=%d", result.doc_id, result.num_chunks)
    except HTTPException:
        raise  # re-raise FastAPI HTTPExceptions as-is
    except Exception as exc:
        logger.exception("save-to-context failed")
        raise HTTPException(status_code=502, detail=f"RAG store failed: {exc}")
    return {"ok": True, "doc_id": result.doc_id}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

async def _query_rag(case_id: str, text: str, line_index: int) -> list[SurfacedItem]:
    async with httpx.AsyncClient(timeout=10.0) as client:
        try:
            resp = await client.post(
                f"{RAG_BASE}/query",
                json={"case_id": case_id, "query": text, "top_k": 3},
            )
            resp.raise_for_status()
            data = resp.json()
        except httpx.HTTPError:
            return []

    results = []
    for chunk in data.get("chunks", [])[:2]:
        if not chunk.get("text"):
            continue
        results.append(SurfacedItem(
            id=chunk.get("doc_id", str(uuid.uuid4())),
            after_line=line_index,
            type="document",
            status="hit",
            label=chunk.get("source", "document"),
            excerpt=chunk["text"][:600],
            relevance=round(float(chunk.get("score", 0.8)), 2),
            url=chunk.get("url") or None,
        ))
    return results


async def _query_courtlistener(text: str, context: list[str], line_index: int) -> list[SurfacedItem]:
    query = _build_search_query(text, context)
    if not query:
        return []

    try:
        cases = await search_opinions(query, page_size=2)
    except Exception:
        return []

    results = []
    for case in cases[:2]:
        citation = case.get("citation") or case.get("date_filed", "")
        label = case["case_name"]
        if citation:
            label += f" ({citation})"
        results.append(SurfacedItem(
            id=case["id"],
            after_line=line_index,
            type="caselaw",
            status="hit",
            label=label,
            excerpt=case.get("snippet", "")[:600] or None,
            relevance=None,
            url=case.get("url") or None,
        ))
    return results
