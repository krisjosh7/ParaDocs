"""
LangGraph subgraph for the research pipeline.

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

from langgraph.graph import StateGraph, START, END

from research.state import ResearchState
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


# ---------------------------------------------------------------------------
# Nodes
# Each node receives the full ResearchState and returns only the fields
# it changes. LangGraph merges the returned dict back into state.
# ---------------------------------------------------------------------------

async def load_context_node(state: ResearchState) -> dict:
    print(f"\n{'='*60}")
    print(f"[RESEARCH] LOAD CONTEXT — case_id={state['case_id']}")
    print(f"{'='*60}")
    result = await load_context(LoadContextRequest(case_id=state["case_id"]))
    print(f"[RESEARCH] Case facts loaded ({len(result.case_facts)} chars)")
    print(f"[RESEARCH] Case facts preview: {result.case_facts[:300]}...")
    return {
        "case_facts": result.case_facts,
        "seen_result_ids": result.seen_result_ids,
        "queries_run": [],
        "all_stored_results": [],
        "top_result_ids": [],
    }


async def generate_queries_node(state: ResearchState) -> dict:
    iteration = state["iteration"] + 1
    print(f"\n{'='*60}")
    print(f"[RESEARCH] GENERATE QUERIES — iteration {iteration}")
    print(f"{'='*60}")
    print(f"[RESEARCH] Prior queries: {state['queries_run']}")
    result = await generate_queries(GenerateQueriesRequest(
        case_facts=state["case_facts"],
        queries_run=state["queries_run"],
        n=3,
    ))
    print(f"[RESEARCH] Generated {len(result.queries_to_run)} queries:")
    for i, q in enumerate(result.queries_to_run, 1):
        print(f"  {i}. {q}")
    return {
        "iteration": iteration,
        "queries_to_run": result.queries_to_run,
        "queries_run": state["queries_run"] + result.queries_to_run,
    }


async def search_node(state: ResearchState) -> dict:
    print(f"\n{'='*60}")
    print(f"[RESEARCH] SEARCH — iteration {state['iteration']}")
    print(f"{'='*60}")
    print(f"[RESEARCH] Queries to run: {state['queries_to_run']}")
    print(f"[RESEARCH] Top result IDs for citation chasing: {state['top_result_ids']}")
    print(f"[RESEARCH] Already seen {len(state['seen_result_ids'])} result IDs")
    result = await search(SearchRequest(
        queries_to_run=state["queries_to_run"],
        iteration=state["iteration"],
        top_result_ids=state["top_result_ids"],
        seen_result_ids=state["seen_result_ids"],
    ))
    print(f"[RESEARCH] Search returned {len(result.raw_results)} new results")
    for r in result.raw_results:
        print(f"  - {r.get('case_name', '?')} (id={r.get('id', '?')})")
    return {"raw_results": result.raw_results}


async def score_node(state: ResearchState) -> dict:
    print(f"\n{'='*60}")
    print(f"[RESEARCH] SCORE — {len(state['raw_results'])} results to score")
    print(f"{'='*60}")
    result = await score(ScoreRequest(
        case_facts=state["case_facts"],
        raw_results=state["raw_results"],
        seen_result_ids=state["seen_result_ids"],
    ))
    print(f"[RESEARCH] {len(result.scored_results)} results passed relevance threshold")
    for r in result.scored_results:
        print(f"  - {r.get('case_name', '?')}: score={r.get('relevance_score', '?')} — {r.get('relevance_reason', '')}")
    print(f"[RESEARCH] Top result IDs for next iteration: {result.top_result_ids}")
    return {
        "scored_results": result.scored_results,
        "top_result_ids": result.top_result_ids,
        "seen_result_ids": result.seen_result_ids,
    }


async def store_node(state: ResearchState) -> dict:
    print(f"\n{'='*60}")
    print(f"[RESEARCH] STORE — {len(state['scored_results'])} results to store")
    print(f"{'='*60}")
    result = await store(StoreRequest(
        case_id=state["case_id"],
        scored_results=state["scored_results"],
        seen_result_ids=state["seen_result_ids"],
    ))
    print(f"[RESEARCH] Stored {len(result.all_stored_results)} results to RAG")
    for r in result.all_stored_results:
        print(f"  - {r.get('case_name', '?')} → rag_doc_id={r.get('rag_doc_id', '?')}")
    total = len(state["all_stored_results"]) + len(result.all_stored_results)
    print(f"[RESEARCH] Running total: {total} stored results")
    return {
        "all_stored_results": state["all_stored_results"] + result.all_stored_results,
        "seen_result_ids": result.seen_result_ids,
    }


async def decide_node(state: ResearchState) -> dict:
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
    else:
        print(f"[RESEARCH] >>> CONTINUING to next iteration")
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
