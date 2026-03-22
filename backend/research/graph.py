"""LangGraph subgraph for the research pipeline.

Topology:
    START
      → load_context
      → generate_queries
      → search
      → score
      → store
      → decide
           ├── "continue" → generate_queries  (loop)
           └── "stop"     → END

Each node calls the corresponding router function directly (no HTTP hop).
The router functions own the business logic; the graph owns the wiring.
"""

import logging

from langgraph.graph import StateGraph, START, END

from research.state import ResearchState
from research.event_bus import emit
from research.router import (
    LoadContextRequest,
    GenerateQueriesRequest,
    SearchRequest,
    ScoreRequest,
    StoreRequest,
    DecideRequest,
    load_context,
    generate_queries,
    search,
    score,
    store,
    decide,
)

_logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Nodes
# Each node receives the full ResearchState and returns only the fields
# it changes. LangGraph merges the returned dict back into state.
# ---------------------------------------------------------------------------

async def load_context_node(state: ResearchState) -> dict:
    cid = state["case_id"]
    print(f"\n{'='*60}")
    print(f"[RESEARCH] LOAD CONTEXT — case_id={cid}")
    print(f"{'='*60}")
    emit(cid, {"type": "status", "status": "running", "phase": "load_context"})
    emit(cid, {"type": "log", "msg": "Loading case context from RAG store..."})
    result = await load_context(LoadContextRequest(case_id=cid))
    print(f"[RESEARCH] Case facts loaded ({len(result.case_facts)} chars)")
    print(f"[RESEARCH] Case facts preview: {result.case_facts[:300]}...")
    emit(cid, {"type": "log", "msg": f"Case context loaded ({len(result.case_facts)} chars)"})
    return {
        "case_facts": result.case_facts,
        "seen_result_ids": result.seen_result_ids,
        "queries_run": [],
        "all_stored_results": [],
        "top_result_ids": [],
    }


async def generate_queries_node(state: ResearchState) -> dict:
    cid = state["case_id"]
    iteration = state["iteration"] + 1
    print(f"\n{'='*60}")
    print(f"[RESEARCH] GENERATE QUERIES — iteration {iteration}")
    print(f"{'='*60}")
    print(f"[RESEARCH] Prior queries: {state['queries_run']}")
    emit(cid, {"type": "log", "msg": f"Generating search queries (iteration {iteration})..."})
    result = await generate_queries(GenerateQueriesRequest(
        case_facts=state["case_facts"],
        queries_run=state["queries_run"],
        n=3,
    ))
    print(f"[RESEARCH] Generated {len(result.queries_to_run)} queries:")
    for i, q in enumerate(result.queries_to_run, 1):
        print(f"  {i}. {q}")
        emit(cid, {"type": "log", "msg": f"Query: \"{q}\""})
    return {
        "iteration": iteration,
        "queries_to_run": result.queries_to_run,
        "queries_run": state["queries_run"] + result.queries_to_run,
    }


async def search_node(state: ResearchState) -> dict:
    cid = state["case_id"]
    print(f"\n{'='*60}")
    print(f"[RESEARCH] SEARCH — iteration {state['iteration']}")
    print(f"{'='*60}")
    print(f"[RESEARCH] Queries to run: {state['queries_to_run']}")
    print(f"[RESEARCH] Top result IDs for citation chasing: {state['top_result_ids']}")
    print(f"[RESEARCH] Already seen {len(state['seen_result_ids'])} result IDs")
    emit(cid, {"type": "log", "msg": "Searching CourtListener..."})
    result = await search(SearchRequest(
        queries_to_run=state["queries_to_run"],
        iteration=state["iteration"],
        top_result_ids=state["top_result_ids"],
        seen_result_ids=state["seen_result_ids"],
    ))
    n = len(result.raw_results)
    print(f"[RESEARCH] Search returned {n} new results")
    for r in result.raw_results:
        print(f"  - {r.get('case_name', '?')} (id={r.get('id', '?')})")
    emit(cid, {"type": "log", "msg": f"Found {n} new sources"})
    emit(cid, {"type": "stats", "found": n})
    return {"raw_results": result.raw_results}


async def score_node(state: ResearchState) -> dict:
    cid = state["case_id"]
    n_raw = len(state["raw_results"])
    print(f"\n{'='*60}")
    print(f"[RESEARCH] SCORE — {n_raw} results to score")
    print(f"{'='*60}")
    emit(cid, {"type": "log", "msg": f"Analyzing {n_raw} sources for relevance..."})
    emit(cid, {"type": "stats", "analyzing": n_raw})
    result = await score(ScoreRequest(
        case_facts=state["case_facts"],
        raw_results=state["raw_results"],
        seen_result_ids=state["seen_result_ids"],
        case_id=cid,
    ))
    n_pass = len(result.scored_results)
    print(f"[RESEARCH] {n_pass} results passed relevance threshold")
    for r in result.scored_results:
        print(f"  - {r.get('case_name', '?')}: score={r.get('relevance_score', '?')} — {r.get('relevance_reason', '')}")
    print(f"[RESEARCH] Top result IDs for next iteration: {result.top_result_ids}")
    emit(cid, {"type": "log", "msg": f"{n_pass} of {n_raw} sources passed relevance threshold"})
    emit(cid, {"type": "stats", "approved": n_pass})
    return {
        "scored_results": result.scored_results,
        "top_result_ids": result.top_result_ids,
        "seen_result_ids": result.seen_result_ids,
    }


async def store_node(state: ResearchState) -> dict:
    cid = state["case_id"]
    n_scored = len(state["scored_results"])
    print(f"\n{'='*60}")
    print(f"[RESEARCH] STORE — {n_scored} results to store")
    print(f"{'='*60}")
    emit(cid, {"type": "log", "msg": f"Saving {n_scored} approved sources..."})
    result = await store(StoreRequest(
        case_id=cid,
        scored_results=state["scored_results"],
        seen_result_ids=state["seen_result_ids"],
    ))
    print(f"[RESEARCH] Stored {len(result.all_stored_results)} results to RAG")
    for r in result.all_stored_results:
        print(f"  - {r.get('case_name', '?')} → rag_doc_id={r.get('rag_doc_id', '?')}")
        emit(cid, {
            "type": "stored_result",
            "case_name": r.get("case_name", "Unknown"),
            "relevance_score": r.get("relevance_score"),
            "relevance_reason": r.get("relevance_reason", ""),
            "url": r.get("url", ""),
            "citation": r.get("citation", ""),
        })
    total = len(state["all_stored_results"]) + len(result.all_stored_results)
    print(f"[RESEARCH] Running total: {total} stored results")
    emit(cid, {"type": "log", "msg": f"Stored {len(result.all_stored_results)} sources (total: {total})"})
    return {
        "all_stored_results": state["all_stored_results"] + result.all_stored_results,
        "seen_result_ids": result.seen_result_ids,
    }


async def decide_node(state: ResearchState) -> dict:
    cid = state["case_id"]
    print(f"\n{'='*60}")
    print(f"[RESEARCH] DECIDE — iteration {state['iteration']}")
    print(f"{'='*60}")
    print(f"[RESEARCH] Scored results this iteration: {len(state['scored_results'])}")
    result = await decide(DecideRequest(
        iteration=state["iteration"],
        scored_results=state["scored_results"],
    ))
    if result.stop_reason:
        print(f"[RESEARCH] >>> STOPPING: {result.stop_reason}")
        reason_label = "Iteration cap reached" if result.stop_reason == "max_iter" else "No new matches found"
        emit(cid, {"type": "log", "msg": f"Research complete — {reason_label}"})
        emit(cid, {"type": "status", "status": "complete", "stop_reason": result.stop_reason})
    else:
        print(f"[RESEARCH] >>> CONTINUING to next iteration")
        emit(cid, {"type": "log", "msg": "Continuing to next iteration..."})
    return {"stop_reason": result.stop_reason}


# ---------------------------------------------------------------------------
# Conditional edge
# Called after decide_node — returns the name of the next node.
# ---------------------------------------------------------------------------

def route_after_decide(state: ResearchState) -> str:
    if state["stop_reason"] is None:
        return "generate_queries"
    return END


# ---------------------------------------------------------------------------
# Build and compile
# ---------------------------------------------------------------------------

def build_research_graph() -> StateGraph:
    builder = StateGraph(ResearchState)

    builder.add_node("load_context", load_context_node)
    builder.add_node("generate_queries", generate_queries_node)
    builder.add_node("search", search_node)
    builder.add_node("score", score_node)
    builder.add_node("store", store_node)
    builder.add_node("decide", decide_node)

    builder.add_edge(START, "load_context")
    builder.add_edge("load_context", "generate_queries")
    builder.add_edge("generate_queries", "search")
    builder.add_edge("search", "score")
    builder.add_edge("score", "store")
    builder.add_edge("store", "decide")

    builder.add_conditional_edges(
        "decide",
        route_after_decide,
        {"generate_queries": "generate_queries", END: END},
    )

    return builder


# Compiled subgraph — import this in main graph or for testing:
#   from research.graph import research_subgraph
#   result = await research_subgraph.ainvoke({"case_id": "...", "iteration": 0, ...})
research_subgraph = build_research_graph().compile()
