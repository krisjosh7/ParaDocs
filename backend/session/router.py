import asyncio
import logging
import os
import tempfile
import uuid
from typing import Optional

import httpx
import yake
from fastapi import APIRouter, HTTPException, UploadFile, File
from pydantic import BaseModel

from research.courtlistener import search_opinions
from rag.router import store_document_for_rag
from schemas import StoreDocumentRequest

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/session", tags=["session"])

RAG_BASE = os.environ.get("RAG_BASE_URL", "http://localhost:8000")
_ELEVENLABS_STT_URL = "https://api.elevenlabs.io/v1/speech-to-text"

# Don't bother querying for one-word answers like "Yes" or "Okay"
MIN_TEXT_LENGTH = 20

# YAKE keyphrase extractor — initialized once, runs in <10ms per call.
# n=3: extract up to 3-word phrases  |  top=6: return top 6 keyphrases
# dedupLim=0.3: aggressively filter near-duplicate phrases
_kw_extractor = yake.KeywordExtractor(
    lan="en", n=3, dedupLim=0.3, top=6, features=None,
)


def _build_search_query(text: str, context: list[str]) -> str:
    """
    Extract keyphrases from transcript text using YAKE, then join them
    into a search query. Falls back to raw text if YAKE finds nothing.
    """
    combined = " ".join(context[-2:] + [text])
    if len(combined.strip()) < MIN_TEXT_LENGTH:
        return ""

    print(f"[YAKE] input ({len(combined)} chars): {combined[:300]}")

    keywords = _kw_extractor.extract_keywords(combined)
    # keywords = [(phrase, score)] — lower score = more relevant
    phrases = [kw for kw, _score in keywords]

    if not phrases:
        return combined.strip()

    query = " ".join(phrases)
    print(f"[YAKE] query: {query}")
    return query

def _elevenlabs_api_key() -> str:
    return os.environ.get("ELEVENLABS_API_KEY", "").strip()


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
    label: str = ""    # case name / title
    excerpt: str = ""  # snippet text
    url: str = ""      # source URL (e.g. CourtListener link)
    # Legacy fields — accept but ignore (old frontend may still send these)
    raw_text: str = ""
    source: str = ""


# ---------------------------------------------------------------------------
# POST /session/transcribe
# ---------------------------------------------------------------------------

@router.post("/transcribe")
async def transcribe(audio: UploadFile = File(...)):
    """
    Accepts a raw audio blob from the browser's MediaRecorder,
    sends it to ElevenLabs Scribe for transcription, and returns the text.
    """
    key = _elevenlabs_api_key()
    if not key:
        raise HTTPException(status_code=500, detail="ELEVENLABS_API_KEY is not set")

    audio_bytes = await audio.read()

    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.post(
            _ELEVENLABS_STT_URL,
            headers={"xi-api-key": key},
            files={"file": ("audio.webm", audio_bytes, "audio/webm")},
            data={"model_id": "scribe_v1", "language_code": "en"},
        )

    if resp.status_code != 200:
        print(f"[ElevenLabs STT] error {resp.status_code}: {resp.text[:200]}")
        return {"text": ""}

    text = resp.json().get("text", "").strip()
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
    label = req.label or req.source or "Saved source"
    excerpt = req.excerpt or req.raw_text or ""
    url = req.url or ""

    parts = [label]
    if url:
        parts.append(f"Source: {url}")
    if excerpt:
        parts.append(f"\n{excerpt}")
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
