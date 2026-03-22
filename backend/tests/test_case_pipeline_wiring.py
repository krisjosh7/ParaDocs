from __future__ import annotations

import json
import sys
import types
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

_FAKE_AGENTIC_JSON = json.dumps(
    {
        "hypotheses": [
            {
                "id": "h1",
                "theory": "Test theory",
                "confidence": 0.7,
                "timeline_label": "primary",
                "supporting_event_refs": [],
            },
        ],
        "tasks": [
            {
                "id": "t1",
                "task": "Verify dates",
                "reason": "weak evidence",
                "source": "weak_evidence",
            },
        ],
        "research_queries": ["statute of limitations employment"],
    },
)

from schemas import Document, Event, IngestRequest, StructuredDocument, SummaryBlock


def _stub_sentence_transformers() -> None:
    """Avoid loading torch/transformers when importing rag.router (CI / broken ML env)."""
    mod = types.ModuleType("sentence_transformers")
    mod.SentenceTransformer = MagicMock()
    mod.util = MagicMock()
    sys.modules["sentence_transformers"] = mod


def _minimal_structured(doc_id: str, case_id: str) -> StructuredDocument:
    return StructuredDocument(
        doc_id=doc_id,
        case_id=case_id,
        events=[
            Event(
                event="Meeting occurred",
                date="2024-01-15",
                source_span="p1",
            ),
            Event(
                event="Follow-up call",
                date="2024-01-20",
                source_span="p2",
            ),
        ],
        summary=SummaryBlock(text="summary"),
    )


def test_ingest_defer_skips_merge_and_timeline() -> None:
    _stub_sentence_transformers()
    import rag.router as rr

    from rag.router import ingest_endpoint

    with (
        patch.object(rr, "delete_chunks_for_doc_id"),
        patch.object(rr, "upsert_text_records"),
        patch.object(rr, "write_structured"),
        patch.object(rr, "write_metadata"),
        patch.object(rr, "append_events_from_ingest") as mock_append,
        patch.object(rr, "rebuild_case_timeline") as mock_rebuild,
    ):
        doc = Document(
            case_id="defer-case",
            doc_id="doc-defer-1",
            raw_text="x",
            source="upload",
            timestamp="2024-01-01T00:00:00+00:00",
        )
        structured = _minimal_structured(doc.doc_id, doc.case_id)
        ingest_endpoint(
            IngestRequest(
                document=doc,
                structured=structured,
                defer_case_index=True,
            ),
        )
        mock_append.assert_not_called()
        mock_rebuild.assert_not_called()


def test_ingest_default_runs_merge_and_timeline() -> None:
    _stub_sentence_transformers()
    import rag.router as rr

    from rag.router import ingest_endpoint

    with (
        patch.object(rr, "delete_chunks_for_doc_id"),
        patch.object(rr, "upsert_text_records"),
        patch.object(rr, "write_structured"),
        patch.object(rr, "write_metadata"),
        patch.object(rr, "append_events_from_ingest") as mock_append,
        patch.object(rr, "rebuild_case_timeline") as mock_rebuild,
    ):
        doc = Document(
            case_id="normal-case",
            doc_id="doc-normal-1",
            raw_text="x",
            source="upload",
            timestamp="2024-01-01T00:00:00+00:00",
        )
        structured = _minimal_structured(doc.doc_id, doc.case_id)
        ingest_endpoint(IngestRequest(document=doc, structured=structured))
        mock_append.assert_called_once()
        mock_rebuild.assert_called_once()


@pytest.mark.asyncio
async def test_run_case_workflow_smoke_with_mocks(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("CASES_ROOT", str(tmp_path))

    _stub_sentence_transformers()
    import rag.router as rr
    from schemas import StoreResponse
    from workflow import initial_case_state, run_case_workflow

    structured = _minimal_structured("doc-smoke-1", "case-smoke")

    def fake_store(_payload):
        case_dir = tmp_path / "case-smoke" / "structured"
        case_dir.mkdir(parents=True)
        (case_dir / "doc-smoke-1.json").write_text(
            json.dumps(structured.model_dump()),
            encoding="utf-8",
        )
        return StoreResponse(doc_id="doc-smoke-1", num_chunks=2, summary="s")

    fake_timelines = {"version": 1, "case_id": "case-smoke", "primary": {"entries": []}}

    async def fake_ainvoke(_state):
        return {
            "all_stored_results": [{"id": "r1"}],
            "stop_reason": "no_new_results",
            "iteration": 1,
        }

    with (
        patch.object(rr, "store_document_for_rag", side_effect=fake_store),
        patch(
            "workflow.nodes.rebuild_timeline.rebuild_case_timeline",
            return_value=fake_timelines,
        ),
        patch(
            "workflow.nodes.run_reasoning_phase.rebuild_case_timeline",
            return_value=fake_timelines,
        ),
        patch(
            "workflow.nodes.run_research_phase.research_subgraph",
        ) as mock_rs,
    ):
        mock_rs.ainvoke = AsyncMock(side_effect=fake_ainvoke)
        state = initial_case_state("case-smoke", "raw body", "upload")
        final = await run_case_workflow(state)

    assert final["documents"] and final["documents"][0]["doc_id"] == "doc-smoke-1"
    assert final["timelines"] == fake_timelines
    assert final["research_results"] == [{"id": "r1"}]
    assert final["research_stop_reason"] == "no_new_results"
    assert final["research_iteration"] == 1
    assert final.get("reasoning_backfill_changes", 0) >= 0
    assert len(final.get("hypotheses") or []) == 0
    assert len(final.get("tasks") or []) == 0
    assert len(final.get("research_queries") or []) == 0


def _single_event_structured(doc_id: str, case_id: str) -> StructuredDocument:
    return StructuredDocument(
        doc_id=doc_id,
        case_id=case_id,
        events=[
            Event(
                event="Sole meeting",
                date="2024-01-15",
                source_span="p1",
            ),
        ],
        # Empty summary keeps confidence mass below threshold (one event ≈ floor only).
        summary=SummaryBlock(text=""),
    )


@pytest.mark.asyncio
async def test_run_case_workflow_skips_research_when_context_too_thin(tmp_path, monkeypatch) -> None:
    """One event and no structured extras: confidence mass below threshold; research skipped."""
    monkeypatch.setenv("CASES_ROOT", str(tmp_path))

    _stub_sentence_transformers()
    import rag.router as rr
    from schemas import StoreResponse
    from workflow import initial_case_state, run_case_workflow

    structured = _single_event_structured("doc-thin-1", "case-thin")

    def fake_store(_payload):
        case_dir = tmp_path / "case-thin" / "structured"
        case_dir.mkdir(parents=True)
        (case_dir / "doc-thin-1.json").write_text(
            json.dumps(structured.model_dump()),
            encoding="utf-8",
        )
        return StoreResponse(doc_id="doc-thin-1", num_chunks=1, summary="s")

    fake_timelines = {"version": 1, "case_id": "case-thin", "primary": {"entries": []}}

    with (
        patch.object(rr, "store_document_for_rag", side_effect=fake_store),
        patch(
            "workflow.nodes.rebuild_timeline.rebuild_case_timeline",
            return_value=fake_timelines,
        ),
        patch(
            "workflow.nodes.run_reasoning_phase.rebuild_case_timeline",
            return_value=fake_timelines,
        ),
    ):
        state = initial_case_state("case-thin", "short", "upload")
        final = await run_case_workflow(state)

    assert final["timelines"] == fake_timelines
    assert final["research_results"] == []
    assert final["research_stop_reason"] == "skipped_insufficient_context"
    assert "reasoning_backfill_changes" in final
    assert len(final.get("hypotheses") or []) == 0


@pytest.mark.asyncio
async def test_run_case_workflow_research_runs_only_once(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("CASES_ROOT", str(tmp_path))

    _stub_sentence_transformers()
    import rag.router as rr
    from schemas import StoreResponse
    from workflow import initial_case_state, run_case_workflow

    structured = _minimal_structured("doc-once-a", "case-once")

    def fake_store_a(_payload):
        case_dir = tmp_path / "case-once" / "structured"
        case_dir.mkdir(parents=True)
        (case_dir / "doc-once-a.json").write_text(
            json.dumps(structured.model_dump()),
            encoding="utf-8",
        )
        return StoreResponse(doc_id="doc-once-a", num_chunks=2, summary="s")

    async def fake_ainvoke(_state):
        return {
            "all_stored_results": [{"id": "r1"}],
            "stop_reason": "no_new_results",
            "iteration": 1,
        }

    fake_timelines = {"version": 1, "case_id": "case-once", "primary": {"entries": []}}

    with (
        patch.object(rr, "store_document_for_rag", side_effect=fake_store_a),
        patch(
            "workflow.nodes.rebuild_timeline.rebuild_case_timeline",
            return_value=fake_timelines,
        ),
        patch(
            "workflow.nodes.run_reasoning_phase.rebuild_case_timeline",
            return_value=fake_timelines,
        ),
        patch(
            "workflow.nodes.run_research_phase.research_subgraph",
        ) as mock_rs,
    ):
        mock_rs.ainvoke = AsyncMock(side_effect=fake_ainvoke)
        first = await run_case_workflow(
            initial_case_state("case-once", "first upload body", "upload"),
        )
        assert first["research_stop_reason"] == "no_new_results"

        structured_b = _minimal_structured("doc-once-b", "case-once")

        def fake_store_b(_payload):
            case_dir = tmp_path / "case-once" / "structured"
            (case_dir / "doc-once-b.json").write_text(
                json.dumps(structured_b.model_dump()),
                encoding="utf-8",
            )
            return StoreResponse(doc_id="doc-once-b", num_chunks=2, summary="s")

        with patch.object(rr, "store_document_for_rag", side_effect=fake_store_b):
            second = await run_case_workflow(
                initial_case_state("case-once", "second upload body", "upload"),
            )

    mock_rs.ainvoke.assert_called_once()
    assert second["research_stop_reason"] == "skipped_already_completed"
    assert second["research_results"] == []


def test_chat_task_path_persists_and_returns_reasoning(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("CASES_ROOT", str(tmp_path))
    _stub_sentence_transformers()
    from fastapi.testclient import TestClient
    from main import app
    from timeline_logic import empty_timeline_payload, write_timelines_json

    cid = "case-chat-task"
    case_dir = tmp_path / cid
    case_dir.mkdir(parents=True)
    (case_dir / "events.json").write_text("[]", encoding="utf-8")
    write_timelines_json(cid, empty_timeline_payload(cid))

    def fake_gen(system: str, user: str) -> str:
        if "legal case reasoning engine" in system.lower():
            return _FAKE_AGENTIC_JSON
        return json.dumps(
            {
                "is_agent_task": True,
                "task": {
                    "task": "Investigate contract signing date",
                    "type": "investigation",
                    "priority": "medium",
                    "status": "pending",
                },
            }
        )

    def _sync_enqueue(cid: str, reason: str, **kw):
        from workflow.reasoning_agent import try_run_agentic

        try_run_agentic(cid, reason=reason, force=kw.get("force", False))

    with (
        patch("workflow.nodes.agentic_reasoning.generate_json", side_effect=fake_gen),
        patch("routes_chat.query_case", return_value=[]),
        patch("routes_chat.chat_messages", return_value="Acknowledged."),
        patch("routes_chat.enqueue_reasoning_job", side_effect=_sync_enqueue),
    ):
        client = TestClient(app)
        r = client.post(
            "/chat",
            json={
                "message": "Figure out when the contract was signed",
                "case_id": cid,
                "chat_history": [],
            },
        )
    assert r.status_code == 200
    body = r.json()
    assert body["task_detected"] is True
    assert body.get("reasoning_refresh_queued") is True
    assert body["reasoning"] is not None
    tasks = body["reasoning"]["tasks"]
    assert any(t.get("source") == "user" for t in tasks)
    assert (tmp_path / cid / "agentic_state.json").is_file()
