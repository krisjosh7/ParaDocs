# LangGraph subgraph definition for the research pipeline.
# This file owns the graph topology: nodes, edges, and the conditional
# branching logic. Node implementations live in router.py; this file
# just wires them together.
#
# Graph structure:
#
#   [START]
#      │
#      ▼
#   load_case_context       ← calls GET /rag/query (teammate) to fetch existing
#      │                       case facts + already-stored result IDs
#      ▼
#   generate_queries        ← calls POST /research/generate-queries
#      │
#      ▼
#   search_courtlistener    ← fan-out: asyncio.gather over POST /research/search
#      │                       one call per query, results merged before next node
#      ▼
#   score_results           ← calls POST /research/score
#      │
#      ▼
#   store_results           ← calls POST /research/store (pass-through to RAG)
#      │
#      ▼
#   decide_next_step        ← calls POST /research/decide
#      │
#      ├── "continue" ──────► generate_queries  (loop, iteration += 1)
#      │
#      └── "stop" ──────────► [END]
#
# Exported:
#   research_subgraph — compiled StateGraph, ready to be embedded in the
#                       top-level graph by the LangGraph teammate
