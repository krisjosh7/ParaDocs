# ResearchState — the shared state TypedDict that flows through every node
# in the research subgraph. This is the single contract between all nodes;
# if a node reads or writes something, it lives here.
#
# Fields (to be defined):
#   case_id          — identifies which case this research run belongs to
#   case_facts       — raw text of the case context loaded at the start
#   queries_run      — list of queries already executed (grows each iteration,
#                      fed back into generate_queries so the LLM avoids repeats)
#   seen_result_ids  — set of CourtListener doc IDs already stored (for dedup)
#   queries_to_run   — batch of queries generated this iteration, consumed by search
#   raw_results      — flattened search results from CourtListener before scoring
#   scored_results   — results that passed the relevance threshold after scoring
#   iteration        — current loop count (used by decide_next_step to enforce cap)
#   stop_reason      — populated by decide_next_step: "max_iter" | "no_new_results"
#                      | "threshold_met" | None (still running)
