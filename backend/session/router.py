import asyncio
import os
import tempfile
import uuid
from typing import Optional

import httpx
import whisper
from fastapi import APIRouter, UploadFile, File
from pydantic import BaseModel

from research.courtlistener import search_opinions

router = APIRouter(prefix="/session", tags=["session"])

RAG_BASE = os.environ.get("RAG_BASE_URL", "http://localhost:8001")

# Don't bother querying for one-word answers like "Yes" or "Okay"
MIN_TEXT_LENGTH = 20

# Load once at startup — takes ~5s for "base", stays in memory for the session
_whisper_model = whisper.load_model("base")


# ---------------------------------------------------------------------------
# Request / Response models
# ---------------------------------------------------------------------------

class SessionQueryRequest(BaseModel):
    case_id: str
    text: str        # the latest transcript line
    line_index: int  # 0-based index in the transcript — echoed back in items


class SurfacedItem(BaseModel):
    id: str
    after_line: int
    type: str            # "document" | "caselaw"
    status: str          # "hit"
    label: str
    excerpt: Optional[str]
    relevance: Optional[float]


class SessionQueryResponse(BaseModel):
    items: list[SurfacedItem]


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
    case_items = await _query_courtlistener(req.text, req.line_index)
    items.extend(case_items)

    return SessionQueryResponse(items=items)


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
            excerpt=chunk["text"][:200],
            relevance=round(float(chunk.get("score", 0.8)), 2),
        ))
    return results


async def _query_courtlistener(text: str, line_index: int) -> list[SurfacedItem]:
    try:
        cases = await search_opinions(text, page_size=2)
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
            excerpt=case.get("snippet", "")[:200] or None,
            relevance=None,
        ))
    return results
