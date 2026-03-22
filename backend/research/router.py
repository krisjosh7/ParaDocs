import asyncio
import os
from datetime import datetime, timezone

import httpx
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from research.courtlistener import (
    search_opinions,
    get_forward_citations,
    get_backward_citations,
)
from research.prompts import run_generate_queries, run_score_result
from research.state import MAX_ITERATIONS, RELEVANCE_THRESHOLD

router = APIRouter(prefix="/research", tags=["research"])

# Base URL for the RAG service (teammate's backend)
RAG_BASE = os.environ.get("RAG_BASE_URL", "http://localhost:8000")


# ---------------------------------------------------------------------------
# Request / Response models
# ---------------------------------------------------------------------------

class LoadContextRequest(BaseModel):
    case_id: str

class LoadContextResponse(BaseModel):
    case_facts: str
    seen_result_ids: list[str]


class GenerateQueriesRequest(BaseModel):
    case_facts: str
    queries_run: list[str]
    n: int = 3

class GenerateQueriesResponse(BaseModel):
    queries_to_run: list[str]


class SearchRequest(BaseModel):
    queries_to_run: list[str]
    iteration: int
    top_result_ids: list[str]   # opinion_ids — used for citation chasing in iter 2+
    seen_result_ids: list[str]  # cluster_ids — used for dedup

class SearchResponse(BaseModel):
    raw_results: list[dict]


class ScoreRequest(BaseModel):
    case_facts: str
    raw_results: list[dict]
    seen_result_ids: list[str]

class ScoreResponse(BaseModel):
    scored_results: list[dict]
    top_result_ids: list[str]    # opinion_ids of top scorers — seeds for next iter
    seen_result_ids: list[str]   # updated with newly scored ids


class StoreRequest(BaseModel):
    case_id: str
    scored_results: list[dict]
    seen_result_ids: list[str]

class StoreResponse(BaseModel):
    all_stored_results: list[dict]
    seen_result_ids: list[str]  # updated with newly stored ids


class DecideRequest(BaseModel):
    iteration: int
    scored_results: list[dict]

class DecideResponse(BaseModel):
    decision: str        # "continue" | "stop"
    stop_reason: str | None


class RunResearchRequest(BaseModel):
    case_id: str

class RunResearchResponse(BaseModel):
    case_id: str
    stop_reason: str
    all_stored_results: list[dict]
    iteration: int


# ---------------------------------------------------------------------------
# POST /research/load-context
# ---------------------------------------------------------------------------

@router.post("/load-context", response_model=LoadContextResponse)
async def load_context(req: LoadContextRequest):
    """
    Entry point for the research subgraph.
    Queries the RAG database to build case_facts from existing documents,
    giving the LLM grounding context for query generation and scoring.

    case_facts is assembled from:
      - The case summary (structured_hits type="summary")
      - Top relevant chunks
      - Parties and claims if available

    seen_result_ids starts empty — dedup accumulates within this run.
    """
    async with httpx.AsyncClient(timeout=15.0) as client:
        try:
            resp = await client.post(
                f"{RAG_BASE}/query",
                json={
                    "case_id": req.case_id,
                    "query": "case summary parties claims events jurisdiction",
                    "top_k": 5,
                },
            )
            resp.raise_for_status()
            rag_data = resp.json()
        except httpx.HTTPError as e:
            raise HTTPException(status_code=502, detail=f"RAG query failed: {e}")

    # Build case_facts from the RAG response
    parts: list[str] = []

    # Prefer the summary structured hit if available
    for hit in rag_data.get("structured_hits", []):
        if hit.get("type") == "summary" and hit.get("value"):
            parts.append(f"Summary: {hit['value']}")
            break

    # Append raw chunks as additional context
    for chunk in rag_data.get("chunks", []):
        if chunk.get("text"):
            parts.append(chunk["text"])

    case_facts = "\n\n".join(parts) if parts else "No existing case context found."

    return LoadContextResponse(
        case_facts=case_facts,
        seen_result_ids=[],  # dedup accumulates within this research run
    )


# ---------------------------------------------------------------------------
# POST /research/generate-queries
# ---------------------------------------------------------------------------

@router.post("/generate-queries", response_model=GenerateQueriesResponse)
async def generate_queries(req: GenerateQueriesRequest):
    """
    Calls the local Ollama LLM to produce N novel legal search queries
    grounded in case_facts, avoiding queries already run.
    """
    queries = run_generate_queries(
        case_facts=req.case_facts,
        queries_run=req.queries_run,
        n=req.n,
    )

    if not queries:
        raise HTTPException(
            status_code=500,
            detail="LLM returned no queries — check Ollama is running and model is available",
        )

    return GenerateQueriesResponse(queries_to_run=queries)


# ---------------------------------------------------------------------------
# POST /research/search
# ---------------------------------------------------------------------------

@router.post("/search", response_model=SearchResponse)
async def search(req: SearchRequest):
    """
    Executes CourtListener searches in parallel.

    Iteration 1:  fan-out text search across all queries_to_run
    Iteration 2+: citation chasing — forward + backward on each top_result_id,
                  plus any new text queries if generate-queries produced them

    Results are flattened and deduplicated against seen_result_ids.
    """
    seen = set(req.seen_result_ids)
    tasks = []

    if req.iteration == 1 or req.queries_to_run:
        # Text search — one task per query
        for query in req.queries_to_run:
            tasks.append(search_opinions(query, page_size=5))

    if req.iteration >= 2 and req.top_result_ids:
        # Citation chasing — forward and backward on each top result
        for opinion_id in req.top_result_ids:
            tasks.append(get_forward_citations(opinion_id))
            tasks.append(get_backward_citations(opinion_id))

    if not tasks:
        return SearchResponse(raw_results=[])

    # Fire all tasks in parallel
    batches = await asyncio.gather(*tasks, return_exceptions=True)

    # Flatten, skip errors, deduplicate
    raw_results: list[dict] = []
    for batch in batches:
        if isinstance(batch, Exception):
            continue  # log in production; don't crash the whole search
        for result in batch:
            if result.get("id") and result["id"] not in seen:
                seen.add(result["id"])
                raw_results.append(result)

    return SearchResponse(raw_results=raw_results)


# ---------------------------------------------------------------------------
# POST /research/score
# ---------------------------------------------------------------------------

@router.post("/score", response_model=ScoreResponse)
async def score(req: ScoreRequest):
    """
    Scores each raw result for relevance against case_facts using the
    local LLM. Filters to results at or above RELEVANCE_THRESHOLD.
    Also deduplicates against seen_result_ids before scoring to avoid
    wasting LLM calls on already-stored results.
    """
    seen = set(req.seen_result_ids)

    # Deduplicate before scoring — no point scoring what's already stored
    to_score = [r for r in req.raw_results if r.get("id") not in seen]

    scored_results: list[dict] = []
    for result in to_score:
        score_val, reason = run_score_result(req.case_facts, result)
        if score_val >= RELEVANCE_THRESHOLD:
            scored_results.append({
                **result,
                "relevance_score": score_val,
                "relevance_reason": reason,
            })

    # Sort descending by score so top results are easy to extract
    scored_results.sort(key=lambda r: r["relevance_score"], reverse=True)

    # Top result opinion_ids become seeds for citation chasing next iteration
    top_result_ids = [
        r["opinion_id"]
        for r in scored_results[:3]
        if r.get("opinion_id")
    ]

    # Update seen_result_ids with everything we scored (pass or fail)
    # so we never re-score the same document
    updated_seen = list(seen | {r["id"] for r in to_score if r.get("id")})

    return ScoreResponse(
        scored_results=scored_results,
        top_result_ids=top_result_ids,
        seen_result_ids=updated_seen,
    )


# ---------------------------------------------------------------------------
# POST /research/store
# ---------------------------------------------------------------------------

@router.post("/store", response_model=StoreResponse)
async def store(req: StoreRequest):
    """
    Passes each scored result to the RAG /store endpoint.
    Owns no storage logic — purely a translation layer between the
    research pipeline's normalized result shape and the RAG store schema.
    """
    stored: list[dict] = []
    seen = set(req.seen_result_ids)

    async with httpx.AsyncClient(timeout=15.0) as client:
        for result in req.scored_results:
            # Format the CourtListener result as readable text for the RAG store.
            # The RAG /parse endpoint will chunk and embed this.
            header = result.get("case_name", "Unknown Case")
            if result.get("citation"):
                header += f" ({result['citation']})"
            if result.get("court"):
                header += f"\nCourt: {result['court']}"
            if result.get("date_filed"):
                header += f"\nDate Filed: {result['date_filed']}"

            raw_text = (
                f"{header}\n"
                f"Source: CourtListener ({result.get('source_type', 'search')})\n"
                f"URL: {result.get('url', '')}\n\n"
                f"{result.get('snippet', '')}"
            )

            payload = {
                "case_id": req.case_id,
                "raw_text": raw_text,
                "source": "web",
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }

            try:
                resp = await client.post(f"{RAG_BASE}/store", json=payload)
                resp.raise_for_status()
                stored.append({**result, "rag_doc_id": resp.json().get("doc_id")})
                seen.add(result["id"])
            except httpx.HTTPError:
                # A single failed store shouldn't abort the batch
                continue

    return StoreResponse(
        all_stored_results=stored,
        seen_result_ids=list(seen),
    )


# ---------------------------------------------------------------------------
# POST /research/decide
# ---------------------------------------------------------------------------

@router.post("/decide", response_model=DecideResponse)
async def decide(req: DecideRequest):
    """
    Pure logic — no LLM, no external calls.
    Determines whether the research loop should continue or stop.

    Stop conditions (checked in priority order):
      1. Hard iteration cap reached (MAX_ITERATIONS)
      2. No new scored results this iteration (diminishing returns)
    """
    if req.iteration >= MAX_ITERATIONS:
        return DecideResponse(decision="stop", stop_reason="max_iter")

    if not req.scored_results:
        return DecideResponse(decision="stop", stop_reason="no_new_results")

    return DecideResponse(decision="continue", stop_reason=None)


# ---------------------------------------------------------------------------
# POST /research/run  — single entry point that drives the full graph
# ---------------------------------------------------------------------------

@router.post("/run", response_model=RunResearchResponse)
async def run_research(req: RunResearchRequest):
    """
    Kicks off the full research pipeline for a given case.
    Initialises ResearchState and invokes the LangGraph subgraph, which
    loops through load-context → generate-queries → search → score → store
    → decide until a termination condition is met.

    The lazy import of research_subgraph avoids a circular import
    (graph.py imports from this module).
    """
    from research.graph import research_subgraph
    from research.state import initial_research_graph_state

    initial = initial_research_graph_state(req.case_id)

    final = await research_subgraph.ainvoke(initial)

    return RunResearchResponse(
        case_id=req.case_id,
        stop_reason=final["stop_reason"] or "",
        all_stored_results=final["all_stored_results"],
        iteration=final["iteration"],
    )
