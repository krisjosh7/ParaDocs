from typing import TypedDict

# Maximum number of research iterations before the graph force-stops.
# Keeps API costs bounded and prevents runaway loops.
MAX_ITERATIONS = 2

# Minimum relevance score (0.0–1.0) for a result to be passed to store.
# Set by the score node based on the LLM's rating.
RELEVANCE_THRESHOLD = 0.6


class ResearchState(TypedDict):
    # ------------------------------------------------------------------
    # Inputs — set once at the start, read-only throughout the graph
    # ------------------------------------------------------------------

    case_id: str
    # Unique identifier for the case being researched.

    case_facts: str
    # Raw text of the case context: uploaded documents, attorney notes,
    # or a summary of the legal situation. This is what every LLM prompt
    # is grounded in, and what relevance scoring compares results against.

    # ------------------------------------------------------------------
    # Iteration tracking — updated by nodes, read by decide_next_step
    # ------------------------------------------------------------------

    iteration: int
    # Current loop count, starting at 1. Compared against MAX_ITERATIONS
    # by decide_next_step to enforce the hard cap.

    stop_reason: str | None
    # Populated by decide_next_step when the graph terminates.
    # Values: "max_iter" | "no_new_results" | None (still running)

    # ------------------------------------------------------------------
    # Query management — grows across iterations
    # ------------------------------------------------------------------

    queries_run: list[str]
    # All queries executed so far across all iterations. Passed into
    # generate_queries each loop so the LLM generates novel angles
    # rather than repeating what's already been searched.

    queries_to_run: list[str]
    # The batch of queries produced by generate_queries in the current
    # iteration. Consumed by the search node (fan-out), then cleared.

    # ------------------------------------------------------------------
    # Result pipeline — flows through search → score → store each iteration
    # ------------------------------------------------------------------

    raw_results: list[dict]
    # Flattened, deduplicated results from all parallel CourtListener
    # searches this iteration. Input to score_results.
    # Each dict matches the normalized shape from courtlistener.py:
    #   id, opinion_id, case_name, citation, all_citations,
    #   court, court_id, date_filed, snippet, url, source_type

    scored_results: list[dict]
    # Results that passed RELEVANCE_THRESHOLD after LLM scoring.
    # Passed to store_results, then accumulated into all_stored_results.

    all_stored_results: list[dict]
    # Accumulates every scored result stored across all iterations.
    # Returned as the final output of the subgraph.

    # ------------------------------------------------------------------
    # Deduplication — prevents re-processing the same documents
    # ------------------------------------------------------------------

    seen_result_ids: list[str]
    # Cluster IDs of every result that has been scored and stored.
    # Using list (not set) for LangGraph serializability — convert to
    # set when doing membership checks:
    #   if result["id"] not in set(state["seen_result_ids"]): ...

    # ------------------------------------------------------------------
    # Citation chasing — bridges iteration 1 (search) to iteration 2+ (citations)
    # ------------------------------------------------------------------

    top_result_ids: list[str]
    # opinion_ids of the highest-scoring results from the previous iteration.
    # Used by generate_queries in iteration 2+ to decide whether to generate
    # new text queries or to chase citations directly via
    # get_forward_citations / get_backward_citations.
    # Populated by score_results, consumed by the search node.
