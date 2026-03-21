# FastAPI router — one endpoint per research subgraph node.
# Each endpoint receives the current ResearchState (or the relevant slice),
# performs its node's logic, and returns the state fields it mutated.
# The LangGraph subgraph (graph.py) calls these endpoints as its nodes.
#
# Endpoints (all POST, all under /research prefix):
#
#   POST /research/generate-queries
#     In:  case_facts, queries_run
#     Out: queries_to_run (new batch of N novel queries)
#     How: LLM call using GENERATE_QUERIES_PROMPT from prompts.py
#
#   POST /research/search
#     In:  a single query string
#     Out: list of raw results for that query
#     How: calls courtlistener.search_opinions(); called in parallel by graph.py
#          (one invocation per query — parallelism handled at the graph layer)
#
#   POST /research/score
#     In:  raw_results, case_facts, seen_result_ids
#     Out: scored_results (filtered to above-threshold, deduplicated)
#     How: LLM call using SCORE_RESULT_PROMPT; drops below-threshold and seen IDs
#
#   POST /research/store
#     In:  scored_results, case_id
#     Out: updated seen_result_ids
#     How: thin pass-through — calls teammate's POST /rag/store for each result;
#          owns NO storage logic itself
#
#   POST /research/decide
#     In:  iteration, scored_results, stop_reason
#     Out: { "decision": "continue" | "stop", "stop_reason": str }
#     How: pure logic, no LLM — checks iteration cap, empty results, etc.
