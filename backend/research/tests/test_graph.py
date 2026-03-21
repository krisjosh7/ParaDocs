"""
Tests for research/graph.py

Strategy:
  - Test the subgraph topology in isolation: does it call the right nodes in order,
    does the conditional edge route correctly, does the loop terminate?
  - Mock all node functions (they're tested separately in test_router.py) so
    graph tests are purely about control flow, not node logic.
  - Integration test runs the full subgraph end-to-end with real services.
"""

import pytest


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

# TODO: fixture — ResearchState with minimal valid fields for a fresh run
# TODO: fixture — mock node functions that return canned state updates


# ---------------------------------------------------------------------------
# Graph topology
# ---------------------------------------------------------------------------

# TODO: test that invoking the subgraph from START reaches store_results
#       in the happy path (mocked nodes, one iteration, results found)
# TODO: test that decide_next_step "continue" routes back to generate_queries
# TODO: test that decide_next_step "stop" routes to END


# ---------------------------------------------------------------------------
# Loop behavior
# ---------------------------------------------------------------------------

# TODO: test that iteration counter increments on each loop
# TODO: test that the graph terminates after MAX_ITERATIONS even if
#       decide_next_step would otherwise return "continue"
# TODO: test that queries_run accumulates across iterations
#       (so generate_queries sees the full history, not just the latest batch)


# ---------------------------------------------------------------------------
# Fan-out (parallel search)
# ---------------------------------------------------------------------------

# TODO: test that search_courtlistener fires one call per query in queries_to_run
# TODO: test that results from all parallel calls are merged before score_results


# ---------------------------------------------------------------------------
# Integration (full subgraph with live services — skip in CI)
# ---------------------------------------------------------------------------

# TODO: @pytest.mark.integration
#       run the subgraph with a real case context, verify it terminates and
#       that stop_reason is set in the final state
