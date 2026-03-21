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
    """
    Entry point. Queries the RAG database to build case_facts from
    existing documents and initialises seen_result_ids for this run.
    """
    result = await load_context(LoadContextRequest(case_id=state["case_id"]))
    return {
        "case_facts": result.case_facts,
        "seen_result_ids": result.seen_result_ids,
        "queries_run": [],
        "all_stored_results": [],
        "top_result_ids": [],
    }


async def generate_queries_node(state: ResearchState) -> dict:
    """
    Increments the iteration counter and asks the LLM to produce
    novel search queries. Passes the full history of prior queries
    so the model explores new angles each loop.
    """
    result = await generate_queries(GenerateQueriesRequest(
        case_facts=state["case_facts"],
        queries_run=state["queries_run"],
        n=3,
    ))
    return {
        "iteration": state["iteration"] + 1,
        "queries_to_run": result.queries_to_run,
        # Accumulate — LLM sees the full history next iteration
        "queries_run": state["queries_run"] + result.queries_to_run,
    }


async def search_node(state: ResearchState) -> dict:
    """
    Iteration 1:  parallel text search across all queries_to_run.
    Iteration 2+: citation chasing on top_result_ids, plus any new
                  text queries if generate_queries produced them.
    Results are deduplicated against seen_result_ids before returning.
    """
    result = await search(SearchRequest(
        queries_to_run=state["queries_to_run"],
        iteration=state["iteration"],
        top_result_ids=state["top_result_ids"],
        seen_result_ids=state["seen_result_ids"],
    ))
    return {"raw_results": result.raw_results}


async def score_node(state: ResearchState) -> dict:
    """
    LLM scores each raw result for relevance. Results below
    RELEVANCE_THRESHOLD are dropped. Updates top_result_ids
    (seeds for citation chasing next iteration) and seen_result_ids.
    """
    result = await score(ScoreRequest(
        case_facts=state["case_facts"],
        raw_results=state["raw_results"],
        seen_result_ids=state["seen_result_ids"],
    ))
    return {
        "scored_results": result.scored_results,
        "top_result_ids": result.top_result_ids,
        "seen_result_ids": result.seen_result_ids,
    }


async def store_node(state: ResearchState) -> dict:
    """
    Passes each scored result to the RAG /store endpoint.
    Accumulates into all_stored_results across iterations.
    """
    result = await store(StoreRequest(
        case_id=state["case_id"],
        scored_results=state["scored_results"],
        seen_result_ids=state["seen_result_ids"],
    ))
    return {
        # Append this iteration's stored results to the running total
        "all_stored_results": state["all_stored_results"] + result.all_stored_results,
        "seen_result_ids": result.seen_result_ids,
    }


async def decide_node(state: ResearchState) -> dict:
    """
    Checks termination conditions. Sets stop_reason if stopping,
    leaves it None if the loop should continue.
    """
    result = await decide(DecideRequest(
        iteration=state["iteration"],
        scored_results=state["scored_results"],
    ))
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
