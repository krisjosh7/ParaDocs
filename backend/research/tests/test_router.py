"""
Tests for research/router.py

Strategy:
  - Use FastAPI's TestClient for endpoint-level tests.
  - Mock all outbound calls (courtlistener.py functions, LLM calls, RAG store)
    so tests are fast and deterministic.
  - Integration tests (marked @pytest.mark.integration) hit the real LLM and
    CourtListener — run manually to validate end-to-end behavior.
"""

import pytest


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

# TODO: fixture — TestClient wrapping the FastAPI app with research router mounted
# TODO: fixture — mock for courtlistener.search_opinions returning 3 fake results
# TODO: fixture — mock for LLM call returning a fixed list of query strings
# TODO: fixture — mock for LLM call returning a fixed relevance score


# ---------------------------------------------------------------------------
# POST /research/generate-queries
# ---------------------------------------------------------------------------

# TODO: test 200 with valid case_facts + empty queries_run returns a list of strings
# TODO: test that queries_run is passed into the LLM prompt (mock captures the call)
# TODO: test 422 if case_facts is missing from the request body


# ---------------------------------------------------------------------------
# POST /research/search
# ---------------------------------------------------------------------------

# TODO: test 200 with a valid query returns normalized result list
# TODO: test that courtlistener.search_opinions is called with the query
# TODO: test 422 if query field is missing


# ---------------------------------------------------------------------------
# POST /research/score
# ---------------------------------------------------------------------------

# TODO: test that results below threshold are filtered out
# TODO: test that IDs already in seen_result_ids are dropped before scoring
# TODO: test that scored_results only contains items above the threshold
# TODO: test empty raw_results returns empty scored_results without LLM call


# ---------------------------------------------------------------------------
# POST /research/store  (pass-through to RAG teammate)
# ---------------------------------------------------------------------------

# TODO: test that one POST to /rag/store is made per item in scored_results
# TODO: test that returned seen_result_ids includes the newly stored IDs
# TODO: test that a failed /rag/store call is logged but doesn't crash the endpoint


# ---------------------------------------------------------------------------
# POST /research/decide
# ---------------------------------------------------------------------------

# TODO: test returns "stop" when iteration >= MAX_ITERATIONS
# TODO: test returns "stop" when scored_results is empty (no new findings)
# TODO: test returns "continue" when below cap and results were found
# TODO: test stop_reason is populated correctly for each termination condition


# ---------------------------------------------------------------------------
# Integration (live LLM + CourtListener — skip in CI)
# ---------------------------------------------------------------------------

# TODO: @pytest.mark.integration
#       POST /research/generate-queries with real case facts returns coherent queries

# TODO: @pytest.mark.integration
#       POST /research/search with a real query returns non-empty results

# TODO: @pytest.mark.integration
#       full chain: generate → search → score on a sample negligence case
