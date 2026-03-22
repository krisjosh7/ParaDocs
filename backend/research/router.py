import asyncio
import logging
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
_logger = logging.getLogger(__name__)

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


class ResearchCaseSummaryOut(BaseModel):
    case_id: str
    unique_sources_count: int
    total_runs: int
    last_run_at: str | None = None
    last_run_added_unique: int | None = None
    last_batch_stored_count: int | None = None
    last_stop_reason: str | None = None
    last_iteration: int | None = None


# ---------------------------------------------------------------------------
# GET /research/cases/{case_id}/summary  — dashboard running totals
# ---------------------------------------------------------------------------


@router.get("/cases/{case_id}/summary", response_model=ResearchCaseSummaryOut)
def get_research_case_summary(case_id: str) -> ResearchCaseSummaryOut:
    from research.case_summary import public_summary

    try:
        d = public_summary(case_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    return ResearchCaseSummaryOut(**d)


# ---------------------------------------------------------------------------
# POST /research/load-context
# ---------------------------------------------------------------------------

@router.post("/load-context", response_model=LoadContextResponse)
async def load_context(req: LoadContextRequest):
    """
    Entry point for the research subgraph.
    Queries the RAG database to build case_facts from existing documents,
    giving the LLM grounding context for query generation and scoring.
    """
    print(f"[load_context] Querying RAG at {RAG_BASE}/query for case_id={req.case_id}")
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
            print(f"[load_context] RAG query FAILED: {e}")
            raise HTTPException(status_code=502, detail=f"RAG query failed: {e}")

    print(f"[load_context] RAG returned {len(rag_data.get('chunks', []))} chunks, {len(rag_data.get('structured_hits', []))} structured hits")

    parts: list[str] = []

    for hit in rag_data.get("structured_hits", []):
        if hit.get("type") == "summary" and hit.get("value"):
            parts.append(f"Summary: {hit['value']}")
            print(f"[load_context] Found summary structured hit")
            break

    for chunk in rag_data.get("chunks", []):
        if chunk.get("text"):
            parts.append(chunk["text"])

    case_facts = "\n\n".join(parts) if parts else "No existing case context found."
    print(f"[load_context] Built case_facts from {len(parts)} parts ({len(case_facts)} chars)")

    return LoadContextResponse(
        case_facts=case_facts,
        seen_result_ids=[],
    )


# ---------------------------------------------------------------------------
# POST /research/generate-queries
# ---------------------------------------------------------------------------

@router.post("/generate-queries", response_model=GenerateQueriesResponse)
async def generate_queries(req: GenerateQueriesRequest):
    """
    Calls the LLM to produce N novel legal search queries
    grounded in case_facts, avoiding queries already run.
    """
    print(f"[generate_queries] Calling LLM for {req.n} queries (prior: {len(req.queries_run)})")
    queries = run_generate_queries(
        case_facts=req.case_facts,
        queries_run=req.queries_run,
        n=req.n,
    )

    if not queries:
        print("[generate_queries] LLM returned NO queries!")
        raise HTTPException(
            status_code=500,
            detail="LLM returned no queries — check Ollama is running and model is available",
        )

    print(f"[generate_queries] LLM returned {len(queries)} queries")
    return GenerateQueriesResponse(queries_to_run=queries)


# ---------------------------------------------------------------------------
# POST /research/search
# ---------------------------------------------------------------------------

@router.post("/search", response_model=SearchResponse)
async def search(req: SearchRequest):
    """
    Executes CourtListener searches in parallel.
    """
    seen = set(req.seen_result_ids)
    tasks = []

    if req.iteration == 1 or req.queries_to_run:
        for query in req.queries_to_run:
            print(f"[search] Queueing text search: '{query}'")
            tasks.append(search_opinions(query, page_size=3))

    if req.iteration >= 2 and req.top_result_ids:
        for opinion_id in req.top_result_ids:
            print(f"[search] Queueing citation chase (fwd+bwd) for opinion {opinion_id}")
            tasks.append(get_forward_citations(opinion_id))
            tasks.append(get_backward_citations(opinion_id))

    if not tasks:
        print("[search] No tasks to run, returning empty")
        return SearchResponse(raw_results=[])

    print(f"[search] Firing {len(tasks)} tasks in parallel...")
    batches = await asyncio.gather(*tasks, return_exceptions=True)

    raw_results: list[dict] = []
    errors = 0
    for batch in batches:
        if isinstance(batch, Exception):
            errors += 1
            print(f"[search] Task error: {batch}")
            continue
        for result in batch:
            if result.get("id") and result["id"] not in seen:
                seen.add(result["id"])
                raw_results.append(result)

    MAX_RAW_RESULTS = 30
    if len(raw_results) > MAX_RAW_RESULTS:
        print(f"[search] Capping results from {len(raw_results)} to {MAX_RAW_RESULTS}")
        raw_results = raw_results[:MAX_RAW_RESULTS]

    print(f"[search] Done: {len(raw_results)} new results, {errors} task errors, {len(seen)} total seen")
    return SearchResponse(raw_results=raw_results)


# ---------------------------------------------------------------------------
# POST /research/score
# ---------------------------------------------------------------------------

SCORE_CONCURRENCY = 2  # max parallel LLM scoring calls


@router.post("/score", response_model=ScoreResponse)
async def score(req: ScoreRequest):
    """
    Scores each raw result for relevance against case_facts using the LLM.
    Runs up to SCORE_CONCURRENCY scoring calls in parallel.
    """
    seen = set(req.seen_result_ids)

    to_score = [r for r in req.raw_results if r.get("id") not in seen]
    print(f"[score] {len(req.raw_results)} raw results, {len(to_score)} after dedup, threshold={RELEVANCE_THRESHOLD}")
    print(f"[score] Scoring in parallel (concurrency={SCORE_CONCURRENCY})")

    semaphore = asyncio.Semaphore(SCORE_CONCURRENCY)

    async def score_one(idx: int, result: dict) -> dict | None:
        case_name = result.get("case_name", "?")
        async with semaphore:
            try:
                print(f"[score] Scoring {idx}/{len(to_score)}: {case_name}...")
                score_val, reason = await asyncio.to_thread(
                    run_score_result, req.case_facts, result
                )
                label = "PASS" if score_val >= RELEVANCE_THRESHOLD else "FAIL"
                print(f"[score]   → {score_val:.2f} {label} — {reason}")
                if score_val >= RELEVANCE_THRESHOLD:
                    return {
                        **result,
                        "relevance_score": score_val,
                        "relevance_reason": reason,
                    }
                return None
            except Exception as e:
                print(f"[score]   → SKIPPED (LLM error): {type(e).__name__}: {e}")
                return None

    tasks = [score_one(i, r) for i, r in enumerate(to_score, 1)]
    results = await asyncio.gather(*tasks)

    scored_results = [r for r in results if r is not None]
    scored_results.sort(key=lambda r: r["relevance_score"], reverse=True)

    top_result_ids = [
        r["opinion_id"]
        for r in scored_results[:3]
        if r.get("opinion_id")
    ]

    updated_seen = list(seen | {r["id"] for r in to_score if r.get("id")})

    print(f"[score] {len(scored_results)} passed threshold, top_ids={top_result_ids}")
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
    """
    stored: list[dict] = []
    seen = set(req.seen_result_ids)

    print(f"[store] Storing {len(req.scored_results)} results to RAG at {RAG_BASE}/store")
    async with httpx.AsyncClient(timeout=120.0) as client:
        for i, result in enumerate(req.scored_results, 1):
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

            source_url = result.get("url", "")

            payload = {
                "case_id": req.case_id,
                "raw_text": raw_text,
                "source": "web",
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "source_url": source_url,
            }

            try:
                print(f"[store] {i}/{len(req.scored_results)}: Storing '{result.get('case_name', '?')}'...")
                resp = await client.post(f"{RAG_BASE}/store", json=payload)
                resp.raise_for_status()
                doc_id = resp.json().get("doc_id")
                stored.append({**result, "rag_doc_id": doc_id})
                seen.add(result["id"])
                print(f"[store]   → stored as rag_doc_id={doc_id}")
            except httpx.HTTPError as e:
                detail = ""
                if hasattr(e, "response") and e.response is not None:
                    detail = f" status={e.response.status_code} body={e.response.text[:200]}"
                print(f"[store]   → FAILED: {type(e).__name__}: {e}{detail}")
                continue
            except Exception as e:
                print(f"[store]   → FAILED (unexpected): {type(e).__name__}: {e}")
                continue

    print(f"[store] Done: {len(stored)}/{len(req.scored_results)} stored successfully")
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
    """
    print(f"[decide] iteration={req.iteration}, MAX={MAX_ITERATIONS}, scored_results={len(req.scored_results)}")
    if req.iteration >= MAX_ITERATIONS:
        print(f"[decide] → STOP (max iterations reached)")
        return DecideResponse(decision="stop", stop_reason="max_iter")

    if not req.scored_results:
        print(f"[decide] → STOP (no new results this iteration)")
        return DecideResponse(decision="stop", stop_reason="no_new_results")

    print(f"[decide] → CONTINUE")
    return DecideResponse(decision="continue", stop_reason=None)


# ---------------------------------------------------------------------------
# POST /research/run  — single entry point that drives the full graph
# ---------------------------------------------------------------------------

@router.post("/run", response_model=RunResearchResponse)
async def run_research(req: RunResearchRequest):
    """
    Kicks off the full research pipeline for a given case.
    """
    from research.graph import research_subgraph
    from research.state import initial_research_graph_state

    print(f"\n{'#'*60}")
    print(f"[RESEARCH PIPELINE] Starting for case_id={req.case_id}")
    print(f"{'#'*60}")

    initial = initial_research_graph_state(req.case_id)
    final = await research_subgraph.ainvoke(initial)

    try:
        from research.case_summary import record_research_run

        record_research_run(
            req.case_id.strip(),
            list(final.get("all_stored_results") or []),
            final.get("stop_reason"),
            int(final.get("iteration") or 0),
        )
    except Exception:
        _logger.exception("Failed to persist research summary for case %s", req.case_id)

    return RunResearchResponse(
        case_id=req.case_id,
        stop_reason=final["stop_reason"] or "",
        all_stored_results=final["all_stored_results"],
        iteration=final["iteration"],
    )
