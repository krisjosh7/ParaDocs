from __future__ import annotations

import json
import sys
import types
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from schemas import Document, Event, IngestRequest, StructuredDocument, SummaryBlock


def _stub_sentence_transformers() -> None:
    """Avoid loading torch/transformers when importing rag.router (CI / broken ML env)."""
    mod = types.ModuleType("sentence_transformers")
    mod.SentenceTransformer = MagicMock()
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
