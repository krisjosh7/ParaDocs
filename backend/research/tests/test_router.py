"""
Tests for research/router.py

Unit tests:        mock all outbound calls — fast, no external services needed
Integration tests: real CourtListener + Ollama, mocked RAG — run manually
"""

import json
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
from httpx import AsyncClient, ASGITransport

from research.state import MAX_ITERATIONS, RELEVANCE_THRESHOLD

# ---------------------------------------------------------------------------
# Shared fixtures and sample data
# ---------------------------------------------------------------------------

CASE_FACTS = (
    "A driver ran a red light at 45mph in a school zone, striking a pedestrian. "
    "We are pursuing a negligence claim based on duty of care and traffic violations."
)

SAMPLE_RESULT = {
    "id": "cluster_001",
    "opinion_id": "op_001",
    "case_name": "Smith v. Jones",
    "citation": "123 F.3d 456",
    "all_citations": ["123 F.3d 456"],
    "court": "9th Circuit",
    "court_id": "ca9",
    "date_filed": "2001-03-15",
    "snippet": "The court held that running a red light constitutes negligence per se.",
    "url": "https://www.courtlistener.com/opinion/123/smith-v-jones/",
    "source_type": "search",
}

SAMPLE_RESULT_2 = {**SAMPLE_RESULT, "id": "cluster_002", "opinion_id": "op_002",
                   "case_name": "Doe v. City"}
SAMPLE_RESULT_3 = {**SAMPLE_RESULT, "id": "cluster_003", "opinion_id": "op_003",
                   "case_name": "Brown v. State"}


@pytest.fixture
async def client():
    """AsyncClient pointed at the FastAPI app — no real network."""
    from main import app
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as c:
        yield c


# ---------------------------------------------------------------------------
# POST /research/load-context
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_load_context_builds_case_facts_from_summary(client):
    rag_response = {
        "chunks": [{"text": "Plaintiff was injured at intersection.", "score": 0.9,
                    "source": "upload", "doc_id": "d1"}],
        "structured_hits": [{"type": "summary", "value": "Negligence case involving a pedestrian.",
                              "confidence": 0.95}],
        "sources": ["d1"],
    }
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.raise_for_status = MagicMock()
    mock_resp.json.return_value = rag_response

    with patch("research.router.httpx.AsyncClient") as mock_client_cls:
        mock_cm = AsyncMock()
        mock_cm.__aenter__.return_value.post = AsyncMock(return_value=mock_resp)
        mock_client_cls.return_value = mock_cm

        r = await client.post("/research/load-context", json={"case_id": "case_1"})

    assert r.status_code == 200
    data = r.json()
    assert "case_facts" in data
    # Summary should appear first
    assert "Negligence case involving a pedestrian" in data["case_facts"]
    assert data["seen_result_ids"] == []


@pytest.mark.asyncio
async def test_load_context_falls_back_to_chunks_when_no_summary(client):
    rag_response = {
        "chunks": [{"text": "Plaintiff crossed at marked crosswalk.", "score": 0.8,
                    "source": "upload", "doc_id": "d1"}],
        "structured_hits": [],
        "sources": ["d1"],
    }
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.raise_for_status = MagicMock()
    mock_resp.json.return_value = rag_response

    with patch("research.router.httpx.AsyncClient") as mock_client_cls:
        mock_cm = AsyncMock()
        mock_cm.__aenter__.return_value.post = AsyncMock(return_value=mock_resp)
        mock_client_cls.return_value = mock_cm

        r = await client.post("/research/load-context", json={"case_id": "case_1"})

    assert r.status_code == 200
    assert "crosswalk" in r.json()["case_facts"]


@pytest.mark.asyncio
async def test_load_context_returns_502_when_rag_is_down(client):
    with patch("research.router.httpx.AsyncClient") as mock_client_cls:
        mock_cm = AsyncMock()
        mock_cm.__aenter__.return_value.post = AsyncMock(
            side_effect=httpx.ConnectError("connection refused")
        )
        mock_client_cls.return_value = mock_cm

        r = await client.post("/research/load-context", json={"case_id": "case_1"})

    assert r.status_code == 502


# ---------------------------------------------------------------------------
# POST /research/generate-queries
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_generate_queries_returns_list(client):
    with patch("research.router.run_generate_queries",
               return_value=["negligence per se", "duty of care", "traffic violation"]):
        r = await client.post("/research/generate-queries", json={
            "case_facts": CASE_FACTS,
            "queries_run": [],
            "n": 3,
        })

    assert r.status_code == 200
    data = r.json()
    assert "queries_to_run" in data
    assert len(data["queries_to_run"]) == 3


@pytest.mark.asyncio
async def test_generate_queries_passes_prior_queries_to_llm(client):
    prior = ["negligence per se"]
    captured = {}

    def mock_generate(case_facts, queries_run, n):
        captured["queries_run"] = queries_run
        return ["duty of care", "reasonable person standard", "traffic ordinance"]

    with patch("research.router.run_generate_queries", side_effect=mock_generate):
        await client.post("/research/generate-queries", json={
            "case_facts": CASE_FACTS,
            "queries_run": prior,
            "n": 3,
        })

    assert captured["queries_run"] == prior


@pytest.mark.asyncio
async def test_generate_queries_returns_500_when_llm_returns_empty(client):
    with patch("research.router.run_generate_queries", return_value=[]):
        r = await client.post("/research/generate-queries", json={
            "case_facts": CASE_FACTS,
            "queries_run": [],
        })

    assert r.status_code == 500


@pytest.mark.asyncio
async def test_generate_queries_422_missing_case_facts(client):
    r = await client.post("/research/generate-queries", json={"queries_run": []})
    assert r.status_code == 422


# ---------------------------------------------------------------------------
# POST /research/search
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_search_iteration_1_uses_text_search(client):
    with patch("research.router.search_opinions",
               new_callable=AsyncMock,
               return_value=[SAMPLE_RESULT]) as mock_search:
        r = await client.post("/research/search", json={
            "queries_to_run": ["negligence per se", "duty of care"],
            "iteration": 1,
            "top_result_ids": [],
            "seen_result_ids": [],
        })

    assert r.status_code == 200
    # One call per query
    assert mock_search.call_count == 2


@pytest.mark.asyncio
async def test_search_iteration_1_does_not_chase_citations(client):
    with patch("research.router.search_opinions",
               new_callable=AsyncMock, return_value=[SAMPLE_RESULT]), \
         patch("research.router.get_forward_citations",
               new_callable=AsyncMock) as mock_fwd, \
         patch("research.router.get_backward_citations",
               new_callable=AsyncMock) as mock_bwd:
        await client.post("/research/search", json={
            "queries_to_run": ["negligence per se"],
            "iteration": 1,
            "top_result_ids": ["op_001"],
            "seen_result_ids": [],
        })

    mock_fwd.assert_not_called()
    mock_bwd.assert_not_called()


@pytest.mark.asyncio
async def test_search_iteration_2_chases_citations(client):
    with patch("research.router.search_opinions",
               new_callable=AsyncMock, return_value=[]), \
         patch("research.router.get_forward_citations",
               new_callable=AsyncMock, return_value=[SAMPLE_RESULT_2]) as mock_fwd, \
         patch("research.router.get_backward_citations",
               new_callable=AsyncMock, return_value=[SAMPLE_RESULT_3]) as mock_bwd:
        r = await client.post("/research/search", json={
            "queries_to_run": [],
            "iteration": 2,
            "top_result_ids": ["op_001"],
            "seen_result_ids": [],
        })

    assert r.status_code == 200
    mock_fwd.assert_called_once_with("op_001")
    mock_bwd.assert_called_once_with("op_001")


@pytest.mark.asyncio
async def test_search_deduplicates_against_seen_ids(client):
    with patch("research.router.search_opinions",
               new_callable=AsyncMock, return_value=[SAMPLE_RESULT, SAMPLE_RESULT_2]):
        r = await client.post("/research/search", json={
            "queries_to_run": ["negligence"],
            "iteration": 1,
            "top_result_ids": [],
            "seen_result_ids": ["cluster_001"],  # SAMPLE_RESULT already seen
        })

    results = r.json()["raw_results"]
    ids = [r["id"] for r in results]
    assert "cluster_001" not in ids
    assert "cluster_002" in ids


@pytest.mark.asyncio
async def test_search_skips_failed_tasks_gracefully(client):
    """One query failing should not crash the whole search."""
    async def flaky_search(query):
        if query == "bad query":
            raise httpx.HTTPError("timeout")
        return [SAMPLE_RESULT]

    with patch("research.router.search_opinions", side_effect=flaky_search):
        r = await client.post("/research/search", json={
            "queries_to_run": ["good query", "bad query"],
            "iteration": 1,
            "top_result_ids": [],
            "seen_result_ids": [],
        })

    assert r.status_code == 200
    assert len(r.json()["raw_results"]) == 1


@pytest.mark.asyncio
async def test_search_empty_queries_and_no_top_ids_returns_empty(client):
    r = await client.post("/research/search", json={
        "queries_to_run": [],
        "iteration": 1,
        "top_result_ids": [],
        "seen_result_ids": [],
    })
    assert r.status_code == 200
    assert r.json()["raw_results"] == []


# ---------------------------------------------------------------------------
# POST /research/score
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_score_filters_below_threshold(client):
    def mock_score(case_facts, result):
        scores = {"cluster_001": 0.9, "cluster_002": 0.2}
        return scores[result["id"]], "reason"

    with patch("research.router.run_score_result", side_effect=mock_score):
        r = await client.post("/research/score", json={
            "case_facts": CASE_FACTS,
            "raw_results": [SAMPLE_RESULT, SAMPLE_RESULT_2],
            "seen_result_ids": [],
        })

    data = r.json()
    scored_ids = [r["id"] for r in data["scored_results"]]
    assert "cluster_001" in scored_ids
    assert "cluster_002" not in scored_ids


@pytest.mark.asyncio
async def test_score_deduplicates_before_scoring(client):
    """Results already in seen_result_ids should not consume LLM calls."""
    call_count = {"n": 0}

    def mock_score(case_facts, result):
        call_count["n"] += 1
        return 0.9, "relevant"

    with patch("research.router.run_score_result", side_effect=mock_score):
        await client.post("/research/score", json={
            "case_facts": CASE_FACTS,
            "raw_results": [SAMPLE_RESULT, SAMPLE_RESULT_2],
            "seen_result_ids": ["cluster_001"],  # already stored
        })

    assert call_count["n"] == 1  # only cluster_002 should be scored


@pytest.mark.asyncio
async def test_score_populates_top_result_ids(client):
    with patch("research.router.run_score_result", return_value=(0.9, "relevant")):
        r = await client.post("/research/score", json={
            "case_facts": CASE_FACTS,
            "raw_results": [SAMPLE_RESULT, SAMPLE_RESULT_2, SAMPLE_RESULT_3],
            "seen_result_ids": [],
        })

    data = r.json()
    assert len(data["top_result_ids"]) <= 3
    assert all(tid in ["op_001", "op_002", "op_003"]
               for tid in data["top_result_ids"])


@pytest.mark.asyncio
async def test_score_empty_raw_results_skips_llm(client):
    with patch("research.router.run_score_result") as mock_score:
        r = await client.post("/research/score", json={
            "case_facts": CASE_FACTS,
            "raw_results": [],
            "seen_result_ids": [],
        })

    mock_score.assert_not_called()
    assert r.json()["scored_results"] == []


@pytest.mark.asyncio
async def test_score_results_sorted_descending(client):
    def mock_score(case_facts, result):
        scores = {"cluster_001": 0.7, "cluster_002": 0.9, "cluster_003": 0.8}
        return scores[result["id"]], "reason"

    with patch("research.router.run_score_result", side_effect=mock_score):
        r = await client.post("/research/score", json={
            "case_facts": CASE_FACTS,
            "raw_results": [SAMPLE_RESULT, SAMPLE_RESULT_2, SAMPLE_RESULT_3],
            "seen_result_ids": [],
        })

    scores = [r["relevance_score"] for r in r.json()["scored_results"]]
    assert scores == sorted(scores, reverse=True)


@pytest.mark.asyncio
async def test_score_updates_seen_result_ids(client):
    with patch("research.router.run_score_result", return_value=(0.9, "relevant")):
        r = await client.post("/research/score", json={
            "case_facts": CASE_FACTS,
            "raw_results": [SAMPLE_RESULT, SAMPLE_RESULT_2],
            "seen_result_ids": ["cluster_003"],
        })

    seen = r.json()["seen_result_ids"]
    assert "cluster_001" in seen
    assert "cluster_002" in seen
    assert "cluster_003" in seen  # original preserved


# ---------------------------------------------------------------------------
# POST /research/store
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_store_calls_rag_once_per_result(client):
    store_resp = MagicMock()
    store_resp.raise_for_status = MagicMock()
    store_resp.json.return_value = {"doc_id": "rag_doc_1", "status": "stored",
                                    "num_chunks": 3, "summary": "..."}

    with patch("research.router.httpx.AsyncClient") as mock_client_cls:
        mock_cm = AsyncMock()
        mock_post = AsyncMock(return_value=store_resp)
        mock_cm.__aenter__.return_value.post = mock_post
        mock_client_cls.return_value = mock_cm

        r = await client.post("/research/store", json={
            "case_id": "case_1",
            "scored_results": [SAMPLE_RESULT, SAMPLE_RESULT_2],
            "seen_result_ids": [],
        })

    assert r.status_code == 200
    assert mock_post.call_count == 2


@pytest.mark.asyncio
async def test_store_includes_rag_doc_id_in_response(client):
    store_resp = MagicMock()
    store_resp.raise_for_status = MagicMock()
    store_resp.json.return_value = {"doc_id": "rag_doc_abc", "status": "stored",
                                    "num_chunks": 2, "summary": "..."}

    with patch("research.router.httpx.AsyncClient") as mock_client_cls:
        mock_cm = AsyncMock()
        mock_cm.__aenter__.return_value.post = AsyncMock(return_value=store_resp)
        mock_client_cls.return_value = mock_cm

        r = await client.post("/research/store", json={
            "case_id": "case_1",
            "scored_results": [SAMPLE_RESULT],
            "seen_result_ids": [],
        })

    stored = r.json()["all_stored_results"]
    assert stored[0]["rag_doc_id"] == "rag_doc_abc"


@pytest.mark.asyncio
async def test_store_skips_failed_results_without_crashing(client):
    call_count = {"n": 0}

    async def flaky_post(url, **kwargs):
        call_count["n"] += 1
        if call_count["n"] == 1:
            raise httpx.HTTPError("store failed")
        resp = MagicMock()
        resp.raise_for_status = MagicMock()
        resp.json.return_value = {"doc_id": "rag_doc_2", "status": "stored",
                                  "num_chunks": 1, "summary": ""}
        return resp

    with patch("research.router.httpx.AsyncClient") as mock_client_cls:
        mock_cm = AsyncMock()
        mock_cm.__aenter__.return_value.post = flaky_post
        mock_client_cls.return_value = mock_cm

        r = await client.post("/research/store", json={
            "case_id": "case_1",
            "scored_results": [SAMPLE_RESULT, SAMPLE_RESULT_2],
            "seen_result_ids": [],
        })

    assert r.status_code == 200
    # First failed, second succeeded
    assert len(r.json()["all_stored_results"]) == 1


@pytest.mark.asyncio
async def test_store_updates_seen_result_ids(client):
    store_resp = MagicMock()
    store_resp.raise_for_status = MagicMock()
    store_resp.json.return_value = {"doc_id": "d1", "status": "stored",
                                    "num_chunks": 1, "summary": ""}

    with patch("research.router.httpx.AsyncClient") as mock_client_cls:
        mock_cm = AsyncMock()
        mock_cm.__aenter__.return_value.post = AsyncMock(return_value=store_resp)
        mock_client_cls.return_value = mock_cm

        r = await client.post("/research/store", json={
            "case_id": "case_1",
            "scored_results": [SAMPLE_RESULT],
            "seen_result_ids": ["cluster_existing"],
        })

    seen = r.json()["seen_result_ids"]
    assert "cluster_001" in seen
    assert "cluster_existing" in seen


# ---------------------------------------------------------------------------
# POST /research/decide  (pure logic — no mocks needed)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_decide_stops_at_max_iterations(client):
    r = await client.post("/research/decide", json={
        "iteration": MAX_ITERATIONS,
        "scored_results": [SAMPLE_RESULT],
    })
    data = r.json()
    assert data["decision"] == "stop"
    assert data["stop_reason"] == "max_iter"


@pytest.mark.asyncio
async def test_decide_stops_when_no_results(client):
    r = await client.post("/research/decide", json={
        "iteration": 1,
        "scored_results": [],
    })
    data = r.json()
    assert data["decision"] == "stop"
    assert data["stop_reason"] == "no_new_results"


@pytest.mark.asyncio
async def test_decide_continues_when_below_cap_with_results(client):
    r = await client.post("/research/decide", json={
        "iteration": 1,
        "scored_results": [SAMPLE_RESULT],
    })
    data = r.json()
    assert data["decision"] == "continue"
    assert data["stop_reason"] is None


@pytest.mark.asyncio
async def test_decide_max_iterations_takes_priority_over_results(client):
    """Even with results, max_iter should stop the loop."""
    r = await client.post("/research/decide", json={
        "iteration": MAX_ITERATIONS,
        "scored_results": [SAMPLE_RESULT, SAMPLE_RESULT_2],
    })
    assert r.json()["decision"] == "stop"
    assert r.json()["stop_reason"] == "max_iter"


# ---------------------------------------------------------------------------
# Integration: real CourtListener + Ollama, mocked RAG
# ---------------------------------------------------------------------------

@pytest.mark.integration
async def test_integration_generate_queries_real_llm(client):
    r = await client.post("/research/generate-queries", json={
        "case_facts": CASE_FACTS,
        "queries_run": [],
        "n": 3,
    })
    assert r.status_code == 200
    queries = r.json()["queries_to_run"]
    assert len(queries) >= 2
    assert all(isinstance(q, str) and q.strip() for q in queries)


@pytest.mark.integration
async def test_integration_search_real_courtlistener(client):
    r = await client.post("/research/search", json={
        "queries_to_run": ["negligence per se traffic violation"],
        "iteration": 1,
        "top_result_ids": [],
        "seen_result_ids": [],
    })
    assert r.status_code == 200
    results = r.json()["raw_results"]
    assert len(results) > 0
    assert all("case_name" in r for r in results)


# ---------------------------------------------------------------------------
# POST /research/run  — end-to-end graph trigger
# ---------------------------------------------------------------------------

FINAL_STATE = {
    "case_id": "case_1",
    "case_facts": "Contract dispute.",
    "iteration": 2,
    "stop_reason": "max_iter",
    "queries_run": ["query A", "query B"],
    "queries_to_run": [],
    "raw_results": [],
    "scored_results": [],
    "all_stored_results": [
        {**SAMPLE_RESULT, "rag_doc_id": "doc-1"},
        {**SAMPLE_RESULT_2, "rag_doc_id": "doc-2"},
    ],
    "seen_result_ids": ["cluster_001", "cluster_002"],
    "top_result_ids": ["op_001"],
}


@pytest.mark.asyncio
async def test_run_research_returns_200_with_stop_reason(client):
    with patch("research.graph.research_subgraph") as mock_graph:
        mock_graph.ainvoke = AsyncMock(return_value=FINAL_STATE)
        r = await client.post("/research/run", json={"case_id": "case_1"})

    assert r.status_code == 200
    data = r.json()
    assert data["stop_reason"] == "max_iter"
    assert data["iteration"] == 2
    assert data["case_id"] == "case_1"


@pytest.mark.asyncio
async def test_run_research_returns_all_stored_results(client):
    with patch("research.graph.research_subgraph") as mock_graph:
        mock_graph.ainvoke = AsyncMock(return_value=FINAL_STATE)
        r = await client.post("/research/run", json={"case_id": "case_1"})

    stored = r.json()["all_stored_results"]
    assert len(stored) == 2
    assert stored[0]["rag_doc_id"] == "doc-1"
    assert stored[1]["rag_doc_id"] == "doc-2"


@pytest.mark.asyncio
async def test_run_research_initialises_empty_state(client):
    """The /run endpoint must pass a clean initial state to ainvoke."""
    captured = {}

    async def capture_invoke(state):
        captured["initial"] = state
        return FINAL_STATE

    with patch("research.graph.research_subgraph") as mock_graph:
        mock_graph.ainvoke = capture_invoke
        await client.post("/research/run", json={"case_id": "case_99"})

    init = captured["initial"]
    assert init["case_id"] == "case_99"
    assert init["iteration"] == 0
    assert init["stop_reason"] is None
    assert init["queries_run"] == []
    assert init["all_stored_results"] == []
    assert init["seen_result_ids"] == []


@pytest.mark.asyncio
async def test_run_research_422_missing_case_id(client):
    r = await client.post("/research/run", json={})
    assert r.status_code == 422


# ---------------------------------------------------------------------------
# Integration: real CourtListener + Ollama, mocked RAG
# ---------------------------------------------------------------------------

@pytest.mark.integration
async def test_integration_full_chain_generate_search_score(client):
    """
    Runs the core pipeline end-to-end: generate → search → score.
    RAG store is not called. Verifies the pipeline produces scored
    results with relevance scores above the threshold.
    """
    # Step 1: generate queries
    gen_r = await client.post("/research/generate-queries", json={
        "case_facts": CASE_FACTS,
        "queries_run": [],
        "n": 2,
    })
    assert gen_r.status_code == 200
    queries = gen_r.json()["queries_to_run"]

    # Step 2: search
    search_r = await client.post("/research/search", json={
        "queries_to_run": queries,
        "iteration": 1,
        "top_result_ids": [],
        "seen_result_ids": [],
    })
    assert search_r.status_code == 200
    raw_results = search_r.json()["raw_results"]
    assert len(raw_results) > 0

    # Step 3: score
    score_r = await client.post("/research/score", json={
        "case_facts": CASE_FACTS,
        "raw_results": raw_results[:3],  # limit to 3 to keep test fast
        "seen_result_ids": [],
    })
    assert score_r.status_code == 200
    scored = score_r.json()["scored_results"]
    # At least one result should pass the threshold for a relevant query
    assert len(scored) > 0
    assert all(r["relevance_score"] >= RELEVANCE_THRESHOLD for r in scored)
