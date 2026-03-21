"""
Tests for research/courtlistener.py

Unit tests:        no network, no token — fast, run in CI
Integration tests: real CourtListener API — set COURTLISTENER_TOKEN to run
"""

import pytest
import httpx

from research.courtlistener import (
    _headers,
    _normalize_search_result,
    search_opinions,
    get_backward_citations,
    get_forward_citations,
    verify_citations,
    API_BASE,
    BASE_URL,
)
from research.tests.conftest import (
    KNOWN_CITATION_TEXT,
    KNOWN_SEARCH_QUERY,
    KNOWN_CASE_SEARCH,
)

# All expected keys in every normalized result — used across multiple tests
EXPECTED_KEYS = {
    "id", "opinion_id", "case_name", "citation", "all_citations",
    "court", "court_id", "date_filed", "snippet", "url", "source_type",
}


# ---------------------------------------------------------------------------
# Unit: _headers
# ---------------------------------------------------------------------------

def test_headers_with_token(monkeypatch):
    monkeypatch.setenv("COURTLISTENER_TOKEN", "testtoken123")
    h = _headers()
    assert h == {"Authorization": "Token testtoken123"}


def test_headers_without_token(monkeypatch):
    monkeypatch.delenv("COURTLISTENER_TOKEN", raising=False)
    assert _headers() == {}


# ---------------------------------------------------------------------------
# Unit: _normalize_search_result
# ---------------------------------------------------------------------------

SAMPLE_SEARCH_RAW = {
    "cluster_id": 6613686,
    "caseName": "Foo v. Bar",
    "citation": ["101 Haw. 235", "65 P.3d 182"],
    "court": "Hawaii Intermediate Court of Appeals",
    "court_id": "hawapp",
    "dateFiled": "2003-01-10",
    "absolute_url": "/opinion/6613686/foo-v-bar/",
    "opinions": [
        {
            "id": 6489975,
            "snippet": "Affirmed in part, reversed in part, vacated and remanded",
            "cites": [],
        }
    ],
}


def test_normalize_search_result_all_keys_present():
    result = _normalize_search_result(SAMPLE_SEARCH_RAW)
    assert EXPECTED_KEYS == set(result.keys())


def test_normalize_search_result_camelcase_fields():
    result = _normalize_search_result(SAMPLE_SEARCH_RAW)
    assert result["case_name"] == "Foo v. Bar"
    assert result["date_filed"] == "2003-01-10"
    assert result["court"] == "Hawaii Intermediate Court of Appeals"


def test_normalize_search_result_ids():
    result = _normalize_search_result(SAMPLE_SEARCH_RAW)
    assert result["id"] == "6613686"
    assert result["opinion_id"] == "6489975"


def test_normalize_search_result_first_citation_extracted():
    result = _normalize_search_result(SAMPLE_SEARCH_RAW)
    assert result["citation"] == "101 Haw. 235"
    assert result["all_citations"] == ["101 Haw. 235", "65 P.3d 182"]


def test_normalize_search_result_empty_citation_list():
    raw = {**SAMPLE_SEARCH_RAW, "citation": []}
    result = _normalize_search_result(raw)
    assert result["citation"] == ""
    assert result["all_citations"] == []


def test_normalize_search_result_snippet_from_nested_opinion():
    result = _normalize_search_result(SAMPLE_SEARCH_RAW)
    assert result["snippet"] == "Affirmed in part, reversed in part, vacated and remanded"


def test_normalize_search_result_snippet_truncated_at_500():
    long_snippet = "x" * 600
    raw = {**SAMPLE_SEARCH_RAW, "opinions": [{"id": 1, "snippet": long_snippet}]}
    result = _normalize_search_result(raw)
    assert len(result["snippet"]) == 500


def test_normalize_search_result_empty_opinions_list():
    raw = {**SAMPLE_SEARCH_RAW, "opinions": []}
    result = _normalize_search_result(raw)
    assert result["opinion_id"] == ""
    assert result["snippet"] == ""


def test_normalize_search_result_url_prefixed_with_base():
    result = _normalize_search_result(SAMPLE_SEARCH_RAW)
    assert result["url"] == f"{BASE_URL}/opinion/6613686/foo-v-bar/"


def test_normalize_search_result_source_type():
    result = _normalize_search_result(SAMPLE_SEARCH_RAW)
    assert result["source_type"] == "search"


# ---------------------------------------------------------------------------
# Integration: search_opinions
# ---------------------------------------------------------------------------

@pytest.mark.integration
async def test_search_opinions_returns_nonempty_list():
    results = await search_opinions(KNOWN_SEARCH_QUERY)
    assert isinstance(results, list)
    assert len(results) > 0, "Expected at least one result for a broad legal query"


@pytest.mark.integration
async def test_search_opinions_result_shape():
    results = await search_opinions(KNOWN_SEARCH_QUERY, page_size=3)
    for r in results:
        assert EXPECTED_KEYS == set(r.keys()), f"Missing keys in result: {EXPECTED_KEYS - set(r.keys())}"


@pytest.mark.integration
async def test_search_opinions_opinion_id_nonempty():
    """
    opinion_id must be non-empty — it's required for citation chasing in
    later iterations. If this fails, _normalize_search_result is broken.
    """
    results = await search_opinions(KNOWN_SEARCH_QUERY, page_size=5)
    for r in results:
        assert r["opinion_id"] != "", f"opinion_id is empty for result: {r['case_name']}"


@pytest.mark.integration
async def test_search_opinions_source_type_is_search():
    results = await search_opinions(KNOWN_SEARCH_QUERY, page_size=3)
    for r in results:
        assert r["source_type"] == "search"


@pytest.mark.integration
async def test_search_opinions_url_is_absolute():
    results = await search_opinions(KNOWN_SEARCH_QUERY, page_size=3)
    for r in results:
        assert r["url"].startswith("https://www.courtlistener.com"), \
            f"URL not absolute: {r['url']}"


@pytest.mark.integration
async def test_search_opinions_with_court_filter():
    # Search API uses `court` (not `court_id`) as the filter parameter
    results = await search_opinions("constitutional rights", page_size=5, filters={"court": "scotus"})
    for r in results:
        assert r["court_id"] == "scotus", f"Expected scotus, got {r['court_id']}"


# ---------------------------------------------------------------------------
# Integration: raw opinion detail shape (diagnostic — reveals opinions_cited format)
# ---------------------------------------------------------------------------

@pytest.mark.integration
async def test_raw_opinion_detail_opinions_cited_field():
    """
    Diagnostic: confirms the exact format of `opinions_cited` in the opinion
    detail response. Chains from a real search so we're not relying on a
    hardcoded ID that may not exist.
    """
    # Get a real opinion_id from a known case
    search_results = await search_opinions(KNOWN_CASE_SEARCH, page_size=1)
    assert search_results, "Search returned no results — can't get a real opinion_id"
    opinion_id = search_results[0]["opinion_id"]
    assert opinion_id, "opinion_id empty in search result"

    async with httpx.AsyncClient(headers=_headers(), timeout=15.0) as client:
        resp = await client.get(f"{API_BASE}/opinions/{opinion_id}/")
        resp.raise_for_status()
        detail = resp.json()

    assert "opinions_cited" in detail, \
        f"opinions_cited field missing. Available keys: {list(detail.keys())}"

    cited = detail["opinions_cited"]
    assert isinstance(cited, list), \
        f"Expected opinions_cited to be a list, got {type(cited)}"

    if cited:
        first = cited[0]
        assert isinstance(first, str), \
            f"Expected URL string, got {type(first)}: {first!r}"
        assert "courtlistener.com" in first, \
            f"Expected full CourtListener URL, got: {first!r}"


# ---------------------------------------------------------------------------
# Integration: get_forward_citations
# ---------------------------------------------------------------------------

@pytest.mark.integration
async def test_get_forward_citations_returns_results():
    """
    Chains from a real search result so we use a genuine opinion_id.
    Miranda v. Arizona is heavily cited — forward citations should exist.
    """
    search_results = await search_opinions(KNOWN_CASE_SEARCH, page_size=1)
    assert search_results, "Search returned no results"
    opinion_id = search_results[0]["opinion_id"]

    results = await get_forward_citations(opinion_id, page_size=5)
    assert isinstance(results, list)
    assert len(results) > 0, \
        f"Expected forward citations for '{KNOWN_CASE_SEARCH}' (opinion_id={opinion_id})"


@pytest.mark.integration
async def test_get_forward_citations_shape():
    search_results = await search_opinions(KNOWN_CASE_SEARCH, page_size=1)
    opinion_id = search_results[0]["opinion_id"]

    results = await get_forward_citations(opinion_id, page_size=3)
    for r in results:
        assert EXPECTED_KEYS == set(r.keys()), f"Missing keys: {EXPECTED_KEYS - set(r.keys())}"
        assert r["source_type"] == "forward_citation"


@pytest.mark.integration
async def test_get_forward_citations_page_size_respected():
    search_results = await search_opinions(KNOWN_CASE_SEARCH, page_size=1)
    opinion_id = search_results[0]["opinion_id"]

    results = await get_forward_citations(opinion_id, page_size=3)
    assert len(results) <= 3


# ---------------------------------------------------------------------------
# Integration: get_backward_citations
# ---------------------------------------------------------------------------

@pytest.mark.integration
async def test_get_backward_citations_returns_list():
    """Chains from a real search result — smoke test, empty list is acceptable."""
    search_results = await search_opinions(KNOWN_CASE_SEARCH, page_size=1)
    opinion_id = search_results[0]["opinion_id"]

    results = await get_backward_citations(opinion_id)
    assert isinstance(results, list)


@pytest.mark.integration
async def test_get_backward_citations_shape():
    search_results = await search_opinions(KNOWN_CASE_SEARCH, page_size=1)
    opinion_id = search_results[0]["opinion_id"]

    results = await get_backward_citations(opinion_id)
    for r in results:
        assert EXPECTED_KEYS == set(r.keys()), f"Missing keys: {EXPECTED_KEYS - set(r.keys())}"
        assert r["source_type"] == "backward_citation"
        assert r["id"] != "", "cluster_id should be populated"
        assert r["case_name"] != "", "case_name should be populated via cluster fetch"


# ---------------------------------------------------------------------------
# Integration: verify_citations
# ---------------------------------------------------------------------------

@pytest.mark.integration
async def test_verify_citations_known_citation():
    results = await verify_citations(KNOWN_CITATION_TEXT)
    assert isinstance(results, list)
    assert len(results) > 0, "Expected at least one citation parsed from known text"

    obergefell = results[0]
    assert obergefell["status"] == 200, \
        f"Expected status 200 for known citation, got {obergefell['status']}: {obergefell.get('error_message')}"
    assert obergefell["citation"] == "576 U.S. 644"
    assert len(obergefell.get("clusters", [])) > 0, "Expected at least one cluster for a valid citation"


@pytest.mark.integration
async def test_verify_citations_no_citations_in_text():
    results = await verify_citations("This text contains no legal citations whatsoever.")
    assert results == [], f"Expected empty list, got {results}"


@pytest.mark.integration
async def test_verify_citations_invalid_citation():
    results = await verify_citations("See 1 U.S. 200 for details.")
    assert len(results) > 0
    assert results[0]["status"] == 404
