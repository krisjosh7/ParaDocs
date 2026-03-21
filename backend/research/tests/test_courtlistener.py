"""
Tests for research/courtlistener.py

Strategy:
  - Unit tests use httpx.MockTransport to intercept HTTP calls — no real network,
    no token required. Fixture responses are minimal but structurally accurate
    CourtListener JSON so we can verify normalization logic.
  - The one live integration test (marked with @pytest.mark.integration) fires a
    real request against CourtListener. Skip it in CI; run manually to confirm
    the actual API shapes match our assumptions, especially:
      * that `opinions_cited` in the detail endpoint returns relative URI strings
      * that the `cites:{id}` query syntax works in forward citation search
"""

import pytest


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

# TODO: fixture — minimal search response JSON matching CourtListener /search/ shape
# TODO: fixture — minimal opinion detail JSON with `opinions_cited` list
# TODO: fixture — MockTransport that returns the above fixtures for specific URLs


# ---------------------------------------------------------------------------
# _normalize
# ---------------------------------------------------------------------------

# TODO: test that camelCase fields (caseName, dateFiled) are mapped correctly
# TODO: test that snake_case fields (case_name, date_filed) are also handled
#       (detail endpoint uses snake_case; search endpoint uses camelCase)
# TODO: test that missing citation list produces empty string, not KeyError
# TODO: test that snippet is truncated to 500 chars when raw text is long
# TODO: test that source_type is passed through unchanged


# ---------------------------------------------------------------------------
# search_opinions
# ---------------------------------------------------------------------------

# TODO: test that query param `q` and `type=o` are sent in the request
# TODO: test that filters dict is merged into params (e.g. court, filed_after)
# TODO: test that the returned list length matches `results` in the mock response
# TODO: test that all items in the returned list have source_type == "search"
# TODO: test HTTP error (non-2xx) raises httpx.HTTPStatusError


# ---------------------------------------------------------------------------
# get_backward_citations
# ---------------------------------------------------------------------------

# TODO: test that the opinion detail endpoint is called with the correct ID
# TODO: test that each URI in `opinions_cited` is resolved with a follow-up GET
# TODO: test that resolution is capped at 10 items even if list is longer
# TODO: test that a failed individual resolution is skipped (continue), not fatal
# TODO: test that returned items have source_type == "backward_citation"


# ---------------------------------------------------------------------------
# get_forward_citations
# ---------------------------------------------------------------------------

# TODO: test that the search is called with `cites:{opinion_id}` in the query
# TODO: test that page_size param is forwarded correctly
# TODO: test that returned items have source_type == "forward_citation"
# TODO: test HTTP error raises httpx.HTTPStatusError


# ---------------------------------------------------------------------------
# Integration (live API — skip in CI)
# ---------------------------------------------------------------------------

# TODO: @pytest.mark.integration
#       test search_opinions("negligence per se") returns at least 1 result
#       and that each result has non-empty id, case_name, url

# TODO: @pytest.mark.integration
#       take the id from above, call get_backward_citations — verify shape
#       (this is the key test to confirm opinions_cited URI format assumption)

# TODO: @pytest.mark.integration
#       call get_forward_citations with same id — verify cites: query syntax works
