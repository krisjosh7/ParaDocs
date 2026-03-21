"""
Tests for research/graph.py

Strategy:
  - route_after_decide: unit tests on the pure routing function
  - Node functions: patch the imported router callables, verify state transforms
  - Full graph: patch all 6 router callables, verify end-to-end control flow
  - Integration: @pytest.mark.integration — real services required

asyncio_mode = auto (pytest.ini) — no @pytest.mark.asyncio needed.
"""

from unittest.mock import AsyncMock, patch

import pytest

from langgraph.graph import END

from research.graph import (
    build_research_graph,
    decide_node,
    generate_queries_node,
    load_context_node,
    research_subgraph,
    route_after_decide,
    score_node,
    search_node,
    store_node,
)
from research.router import (
    DecideResponse,
    GenerateQueriesResponse,
    LoadContextResponse,
    ScoreResponse,
    SearchResponse,
    StoreResponse,
)
from research.state import MAX_ITERATIONS, ResearchState


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def minimal_state(**overrides) -> ResearchState:
    """ResearchState with all fields set to safe, empty defaults."""
    base: ResearchState = {
        "case_id": "test-case-001",
        "case_facts": "Plaintiff sues defendant for breach of contract.",
        "iteration": 0,
        "stop_reason": None,
        "queries_run": [],
        "queries_to_run": [],
        "raw_results": [],
        "scored_results": [],
        "all_stored_results": [],
        "seen_result_ids": [],
        "top_result_ids": [],
    }
    base.update(overrides)
    return base


FAKE_RESULT = {
    "id": "cluster-1",
    "opinion_id": "opinion-1",
    "case_name": "Test v. Test",
    "citation": "123 F.3d 456",
    "all_citations": ["123 F.3d 456"],
    "court": "Court of Appeals",
    "court_id": "ca1",
    "date_filed": "2020-01-01",
    "snippet": "Relevant legal text.",
    "url": "https://www.courtlistener.com/opinion/1/test/",
    "source_type": "search",
}

SCORED_RESULT = {
    **FAKE_RESULT,
    "relevance_score": 0.9,
    "relevance_reason": "Directly addresses breach of contract elements.",
}


# ---------------------------------------------------------------------------
# route_after_decide — pure function, no mocking needed
# ---------------------------------------------------------------------------

def test_route_continue_when_stop_reason_is_none():
    assert route_after_decide(minimal_state(stop_reason=None)) == "generate_queries"


def test_route_to_end_on_max_iter():
    assert route_after_decide(minimal_state(stop_reason="max_iter")) == END


def test_route_to_end_on_no_new_results():
    assert route_after_decide(minimal_state(stop_reason="no_new_results")) == END


# ---------------------------------------------------------------------------
# load_context_node
# ---------------------------------------------------------------------------

async def test_load_context_node_resets_accumulators():
    """
    load_context_node must reset all per-run lists regardless of
    what was in the state before (e.g. a retry scenario).
    """
    resp = LoadContextResponse(
        case_facts="Employment discrimination case.",
        seen_result_ids=[],
    )
    with patch("research.graph.load_context", AsyncMock(return_value=resp)):
        result = await load_context_node(minimal_state())

    assert result["case_facts"] == "Employment discrimination case."
    assert result["seen_result_ids"] == []
    assert result["queries_run"] == []
    assert result["all_stored_results"] == []
    assert result["top_result_ids"] == []


# ---------------------------------------------------------------------------
# generate_queries_node
# ---------------------------------------------------------------------------

async def test_generate_queries_node_increments_iteration():
    state = minimal_state(iteration=0, queries_run=[])
    resp = GenerateQueriesResponse(queries_to_run=["query A", "query B", "query C"])
    with patch("research.graph.generate_queries", AsyncMock(return_value=resp)):
        result = await generate_queries_node(state)

    assert result["iteration"] == 1
    assert result["queries_to_run"] == ["query A", "query B", "query C"]


async def test_generate_queries_node_accumulates_queries_run():
    """queries_run must grow — LLM needs the full history to avoid repeats."""
    prior = ["prior query 1", "prior query 2"]
    state = minimal_state(iteration=1, queries_run=prior)
    resp = GenerateQueriesResponse(queries_to_run=["new query"])
    with patch("research.graph.generate_queries", AsyncMock(return_value=resp)):
        result = await generate_queries_node(state)

    assert result["queries_run"] == ["prior query 1", "prior query 2", "new query"]
    assert result["iteration"] == 2


# ---------------------------------------------------------------------------
# search_node
# ---------------------------------------------------------------------------

async def test_search_node_returns_raw_results():
    state = minimal_state(queries_to_run=["breach of contract"], iteration=1)
    resp = SearchResponse(raw_results=[FAKE_RESULT])
    with patch("research.graph.search", AsyncMock(return_value=resp)):
        result = await search_node(state)

    assert result["raw_results"] == [FAKE_RESULT]


async def test_search_node_empty_results():
    state = minimal_state(queries_to_run=["very obscure query"], iteration=1)
    resp = SearchResponse(raw_results=[])
    with patch("research.graph.search", AsyncMock(return_value=resp)):
        result = await search_node(state)

    assert result["raw_results"] == []


# ---------------------------------------------------------------------------
# score_node
# ---------------------------------------------------------------------------

async def test_score_node_updates_all_score_fields():
    state = minimal_state(
        case_facts="Contract dispute.",
        raw_results=[FAKE_RESULT],
        seen_result_ids=[],
    )
    resp = ScoreResponse(
        scored_results=[SCORED_RESULT],
        top_result_ids=["opinion-1"],
        seen_result_ids=["cluster-1"],
    )
    with patch("research.graph.score", AsyncMock(return_value=resp)):
        result = await score_node(state)

    assert result["scored_results"] == [SCORED_RESULT]
    assert result["top_result_ids"] == ["opinion-1"]
    assert result["seen_result_ids"] == ["cluster-1"]


# ---------------------------------------------------------------------------
# store_node
# ---------------------------------------------------------------------------

async def test_store_node_appends_to_all_stored_results():
    """
    store_node must append this iteration's results to the running total,
    not replace it. all_stored_results is the subgraph's final output.
    """
    prior = [{"id": "cluster-0", "rag_doc_id": "doc-0"}]
    state = minimal_state(
        all_stored_results=prior,
        scored_results=[SCORED_RESULT],
        seen_result_ids=["cluster-0"],
    )
    new_stored = {**SCORED_RESULT, "rag_doc_id": "doc-1"}
    resp = StoreResponse(
        all_stored_results=[new_stored],
        seen_result_ids=["cluster-0", "cluster-1"],
    )
    with patch("research.graph.store", AsyncMock(return_value=resp)):
        result = await store_node(state)

    assert result["all_stored_results"] == prior + [new_stored]  # NOT just [new_stored]
    assert result["seen_result_ids"] == ["cluster-0", "cluster-1"]


async def test_store_node_empty_scored_results():
    state = minimal_state(scored_results=[], all_stored_results=[])
    resp = StoreResponse(all_stored_results=[], seen_result_ids=[])
    with patch("research.graph.store", AsyncMock(return_value=resp)):
        result = await store_node(state)

    assert result["all_stored_results"] == []


# ---------------------------------------------------------------------------
# decide_node
# ---------------------------------------------------------------------------

async def test_decide_node_propagates_stop_reason():
    state = minimal_state(iteration=3, scored_results=[])
    resp = DecideResponse(decision="stop", stop_reason="max_iter")
    with patch("research.graph.decide", AsyncMock(return_value=resp)):
        result = await decide_node(state)

    assert result["stop_reason"] == "max_iter"


async def test_decide_node_none_stop_reason_on_continue():
    state = minimal_state(iteration=1, scored_results=[SCORED_RESULT])
    resp = DecideResponse(decision="continue", stop_reason=None)
    with patch("research.graph.decide", AsyncMock(return_value=resp)):
        result = await decide_node(state)

    assert result["stop_reason"] is None


# ---------------------------------------------------------------------------
# Full graph — topology and control flow
# ---------------------------------------------------------------------------

def _patch_all(
    *,
    load_resp: LoadContextResponse,
    gen_resp: GenerateQueriesResponse,
    search_resp: SearchResponse,
    score_resp: ScoreResponse,
    store_resp: StoreResponse,
    decide_mock: AsyncMock,
):
    """Context manager that patches all 6 router callables in research.graph."""
    from contextlib import ExitStack
    stack = ExitStack()
    stack.enter_context(patch("research.graph.load_context",    AsyncMock(return_value=load_resp)))
    stack.enter_context(patch("research.graph.generate_queries", AsyncMock(return_value=gen_resp)))
    stack.enter_context(patch("research.graph.search",           AsyncMock(return_value=search_resp)))
    stack.enter_context(patch("research.graph.score",            AsyncMock(return_value=score_resp)))
    stack.enter_context(patch("research.graph.store",            AsyncMock(return_value=store_resp)))
    stack.enter_context(patch("research.graph.decide",           decide_mock))
    return stack


async def test_graph_completes_one_iteration():
    """Happy path: all nodes fire once, decide returns stop."""
    load_resp   = LoadContextResponse(case_facts="Case facts.", seen_result_ids=[])
    gen_resp    = GenerateQueriesResponse(queries_to_run=["query A"])
    search_resp = SearchResponse(raw_results=[FAKE_RESULT])
    score_resp  = ScoreResponse(
        scored_results=[SCORED_RESULT],
        top_result_ids=["opinion-1"],
        seen_result_ids=["cluster-1"],
    )
    store_resp  = StoreResponse(
        all_stored_results=[{**SCORED_RESULT, "rag_doc_id": "doc-1"}],
        seen_result_ids=["cluster-1"],
    )
    mock_decide = AsyncMock(return_value=DecideResponse(decision="stop", stop_reason="max_iter"))

    with _patch_all(
        load_resp=load_resp, gen_resp=gen_resp, search_resp=search_resp,
        score_resp=score_resp, store_resp=store_resp, decide_mock=mock_decide,
    ):
        graph = build_research_graph().compile()
        final = await graph.ainvoke(minimal_state())

    assert final["stop_reason"] == "max_iter"
    assert final["iteration"] == 1
    assert len(final["all_stored_results"]) == 1
    mock_decide.assert_awaited_once()


async def test_graph_loops_and_terminates():
    """decide returns 'continue' first, then 'stop' — graph should run exactly 2 iterations."""
    load_resp   = LoadContextResponse(case_facts="Case facts.", seen_result_ids=[])
    gen_resp    = GenerateQueriesResponse(queries_to_run=["query A"])
    search_resp = SearchResponse(raw_results=[FAKE_RESULT])
    score_resp  = ScoreResponse(
        scored_results=[SCORED_RESULT],
        top_result_ids=["opinion-1"],
        seen_result_ids=["cluster-1"],
    )
    store_resp  = StoreResponse(
        all_stored_results=[{**SCORED_RESULT, "rag_doc_id": "doc-1"}],
        seen_result_ids=["cluster-1"],
    )
    mock_decide = AsyncMock(side_effect=[
        DecideResponse(decision="continue", stop_reason=None),
        DecideResponse(decision="stop",    stop_reason="no_new_results"),
    ])

    with _patch_all(
        load_resp=load_resp, gen_resp=gen_resp, search_resp=search_resp,
        score_resp=score_resp, store_resp=store_resp, decide_mock=mock_decide,
    ):
        graph = build_research_graph().compile()
        final = await graph.ainvoke(minimal_state())

    assert final["stop_reason"] == "no_new_results"
    assert final["iteration"] == 2
    assert mock_decide.await_count == 2


async def test_graph_queries_run_accumulates_across_iterations():
    """
    queries_run must contain all queries from all iterations so that
    generate_queries can avoid repeating them.
    """
    load_resp    = LoadContextResponse(case_facts="Case facts.", seen_result_ids=[])
    gen_resp_1   = GenerateQueriesResponse(queries_to_run=["iter 1 query"])
    gen_resp_2   = GenerateQueriesResponse(queries_to_run=["iter 2 query"])
    search_resp  = SearchResponse(raw_results=[FAKE_RESULT])
    score_resp   = ScoreResponse(
        scored_results=[SCORED_RESULT],
        top_result_ids=["opinion-1"],
        seen_result_ids=["cluster-1"],
    )
    store_resp   = StoreResponse(
        all_stored_results=[{**SCORED_RESULT, "rag_doc_id": "doc-1"}],
        seen_result_ids=["cluster-1"],
    )

    mock_generate = AsyncMock(side_effect=[gen_resp_1, gen_resp_2])
    mock_decide   = AsyncMock(side_effect=[
        DecideResponse(decision="continue", stop_reason=None),
        DecideResponse(decision="stop",    stop_reason="no_new_results"),
    ])

    with (
        patch("research.graph.load_context",    AsyncMock(return_value=load_resp)),
        patch("research.graph.generate_queries", mock_generate),
        patch("research.graph.search",           AsyncMock(return_value=search_resp)),
        patch("research.graph.score",            AsyncMock(return_value=score_resp)),
        patch("research.graph.store",            AsyncMock(return_value=store_resp)),
        patch("research.graph.decide",           mock_decide),
    ):
        graph = build_research_graph().compile()
        final = await graph.ainvoke(minimal_state())

    # Both iterations' queries should be present in the final state
    assert "iter 1 query" in final["queries_run"]
    assert "iter 2 query" in final["queries_run"]


async def test_graph_all_stored_results_accumulates_across_iterations():
    """all_stored_results must grow across iterations, not reset each time."""
    load_resp   = LoadContextResponse(case_facts="Case facts.", seen_result_ids=[])
    gen_resp    = GenerateQueriesResponse(queries_to_run=["query A"])
    search_resp = SearchResponse(raw_results=[FAKE_RESULT])
    score_resp  = ScoreResponse(
        scored_results=[SCORED_RESULT],
        top_result_ids=["opinion-1"],
        seen_result_ids=["cluster-1"],
    )

    stored_iter1 = {**SCORED_RESULT, "id": "cluster-1", "rag_doc_id": "doc-1"}
    stored_iter2 = {**SCORED_RESULT, "id": "cluster-2", "rag_doc_id": "doc-2"}

    mock_store  = AsyncMock(side_effect=[
        StoreResponse(all_stored_results=[stored_iter1], seen_result_ids=["cluster-1"]),
        StoreResponse(all_stored_results=[stored_iter2], seen_result_ids=["cluster-1", "cluster-2"]),
    ])
    mock_decide = AsyncMock(side_effect=[
        DecideResponse(decision="continue", stop_reason=None),
        DecideResponse(decision="stop",    stop_reason="no_new_results"),
    ])

    with (
        patch("research.graph.load_context",    AsyncMock(return_value=load_resp)),
        patch("research.graph.generate_queries", AsyncMock(return_value=gen_resp)),
        patch("research.graph.search",           AsyncMock(return_value=search_resp)),
        patch("research.graph.score",            AsyncMock(return_value=score_resp)),
        patch("research.graph.store",            mock_store),
        patch("research.graph.decide",           mock_decide),
    ):
        graph = build_research_graph().compile()
        final = await graph.ainvoke(minimal_state())

    assert len(final["all_stored_results"]) == 2
    assert final["all_stored_results"][0]["rag_doc_id"] == "doc-1"
    assert final["all_stored_results"][1]["rag_doc_id"] == "doc-2"


async def test_graph_terminates_at_max_iterations():
    """
    The decide node enforces MAX_ITERATIONS. After MAX_ITERATIONS loops the
    graph must be in the stopped state regardless of result quality.
    """
    load_resp   = LoadContextResponse(case_facts="Case facts.", seen_result_ids=[])
    gen_resp    = GenerateQueriesResponse(queries_to_run=["query A"])
    search_resp = SearchResponse(raw_results=[FAKE_RESULT])
    score_resp  = ScoreResponse(
        scored_results=[SCORED_RESULT],
        top_result_ids=["opinion-1"],
        seen_result_ids=["cluster-1"],
    )
    store_resp  = StoreResponse(
        all_stored_results=[{**SCORED_RESULT, "rag_doc_id": "doc-1"}],
        seen_result_ids=["cluster-1"],
    )

    # decide always says "continue" until the hard cap from decide logic kicks in;
    # here we simulate what decide *would* return at MAX_ITERATIONS
    decide_responses = [DecideResponse(decision="continue", stop_reason=None)] * (MAX_ITERATIONS - 1)
    decide_responses.append(DecideResponse(decision="stop", stop_reason="max_iter"))
    mock_decide = AsyncMock(side_effect=decide_responses)

    with _patch_all(
        load_resp=load_resp, gen_resp=gen_resp, search_resp=search_resp,
        score_resp=score_resp, store_resp=store_resp, decide_mock=mock_decide,
    ):
        graph = build_research_graph().compile()
        final = await graph.ainvoke(minimal_state())

    assert final["stop_reason"] == "max_iter"
    assert final["iteration"] == MAX_ITERATIONS
    assert mock_decide.await_count == MAX_ITERATIONS


# ---------------------------------------------------------------------------
# Integration — full subgraph with live CourtListener + Ollama + RAG
# ---------------------------------------------------------------------------

@pytest.mark.integration
async def test_graph_integration_terminates(skip_integration_without_token):  # noqa: F811
    """
    End-to-end smoke test: the subgraph must terminate with a stop_reason set.
    Requires: COURTLISTENER_TOKEN, Ollama (llama3.1:8b), RAG service on :8001.
    """
    import httpx
    import os

    # Skip if RAG service is not reachable
    rag_base = os.environ.get("RAG_BASE_URL", "http://localhost:8001")
    try:
        async with httpx.AsyncClient(timeout=3.0) as client:
            await client.get(f"{rag_base}/health")
    except httpx.HTTPError:
        pytest.skip("RAG service not reachable — skipping graph integration test")

    initial: ResearchState = {
        "case_id": "integration-test-001",
        "case_facts": "",
        "iteration": 0,
        "stop_reason": None,
        "queries_run": [],
        "queries_to_run": [],
        "raw_results": [],
        "scored_results": [],
        "all_stored_results": [],
        "seen_result_ids": [],
        "top_result_ids": [],
    }

    final = await research_subgraph.ainvoke(initial)

    assert final["stop_reason"] is not None, "Graph must always terminate with a stop_reason"
    assert final["iteration"] >= 1
