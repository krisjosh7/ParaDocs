"""
Integration tests: FastAPI + Chroma + filesystem under rag_isolation (fake embeddings).
No Ollama required.
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from main import app
from schemas import (
    Claim,
    Document,
    Event,
    JurisdictionBlock,
    StructuredDocument,
    SummaryBlock,
)


def _chroma_count_doc(doc_id: str) -> int:
    import rag.vector_store as vector_store

    col = vector_store.get_collection()
    res = col.get(where={"doc_id": doc_id})
    return len(res.get("ids") or [])


def _chroma_count_case(case_id: str) -> int:
    import rag.vector_store as vector_store

    col = vector_store.get_collection()
    res = col.get(where={"case_id": case_id})
    return len(res.get("ids") or [])


@pytest.fixture
def client(rag_isolation):
    return TestClient(app)


@pytest.mark.integration
def test_integration_ingest_writes_structured_and_audit_on_disk(client, rag_isolation) -> None:
    """Ingest persists structured JSON + audit metadata; raw file is `/store` only."""
    cases_root: Path = rag_isolation["cases"]
    doc = Document(
        case_id="int-case-1",
        doc_id="int-doc-1",
        raw_text="Paragraph one about Omega LLC.\n\nParagraph two about damages.",
        source="upload",
        timestamp="2025-03-01T12:00:00+00:00",
    )
    structured = StructuredDocument(
        doc_id="int-doc-1",
        case_id="int-case-1",
        summary=SummaryBlock(text="Omega dispute summary.", confidence=0.85),
        jurisdiction=JurisdictionBlock(value="Virginia", confidence=0.4),
        events=[
            Event(
                event="Complaint filed",
                date="2025-02-01",
                confidence=0.9,
                source_span="Paragraph one about Omega LLC.",
            )
        ],
        claims=[Claim(type="breach", confidence=0.8, source_span="damages")],
    )
    r = client.post("/ingest", json={"document": doc.model_dump(), "structured": structured.model_dump()})
    assert r.status_code == 200
    body = r.json()
    assert body["doc_id"] == "int-doc-1"
    assert body["num_chunks"] == _chroma_count_doc("int-doc-1")

    base = cases_root / "int-case-1"
    assert not (base / "documents" / "int-doc-1.txt").exists()
    sj = json.loads((base / "structured" / "int-doc-1.json").read_text(encoding="utf-8"))
    assert sj["summary"]["text"] == "Omega dispute summary."
    mj = json.loads((base / "metadata" / "int-doc-1.json").read_text(encoding="utf-8"))
    assert mj["status"] == "ingested"
    assert mj["num_chunks"] == body["num_chunks"]


@pytest.mark.integration
def test_integration_reingest_replaces_vectors_not_accumulates(client, rag_isolation) -> None:
    doc_id = "int-doc-re"
    case_id = "int-case-re"
    doc1 = Document(
        case_id=case_id,
        doc_id=doc_id,
        raw_text="Short first version.",
        source="upload",
        timestamp="2025-01-01T00:00:00+00:00",
    )
    s1 = StructuredDocument(
        doc_id=doc_id,
        case_id=case_id,
        summary=SummaryBlock(text="S1", confidence=1.0),
        jurisdiction=JurisdictionBlock(),
    )
    r1 = client.post("/ingest", json={"document": doc1.model_dump(), "structured": s1.model_dump()})
    assert r1.status_code == 200
    n1 = _chroma_count_doc(doc_id)

    doc2 = Document(
        case_id=case_id,
        doc_id=doc_id,
        raw_text="Much longer second version.\n\n" * 20 + "extra tail.",
        source="tts",
        timestamp="2025-02-01T00:00:00+00:00",
    )
    s2 = StructuredDocument(
        doc_id=doc_id,
        case_id=case_id,
        summary=SummaryBlock(text="S2", confidence=1.0),
        jurisdiction=JurisdictionBlock(),
        events=[Event(event="e", date=None, confidence=0.5, source_span="extra tail.")],
    )
    r2 = client.post("/ingest", json={"document": doc2.model_dump(), "structured": s2.model_dump()})
    assert r2.status_code == 200
    n2 = _chroma_count_doc(doc_id)
    assert n2 == r2.json()["num_chunks"]
    assert n2 != n1


@pytest.mark.integration
def test_integration_multi_document_same_case_sources_and_counts(client, rag_isolation) -> None:
    case_id = "int-multi"
    for i, letter in enumerate(("alpha", "beta")):
        doc = Document(
            case_id=case_id,
            doc_id=f"int-md-{i}",
            raw_text=f"Document {letter} discusses unique keyword {letter}only.",
            source="upload",
            timestamp="2025-01-01T00:00:00+00:00",
        )
        st = StructuredDocument(
            doc_id=f"int-md-{i}",
            case_id=case_id,
            summary=SummaryBlock(text=f"Summary {letter}", confidence=1.0),
            jurisdiction=JurisdictionBlock(),
        )
        assert client.post("/ingest", json={"document": doc.model_dump(), "structured": st.model_dump()}).status_code == 200

    assert _chroma_count_case(case_id) >= 2
    qr = client.post(
        "/query",
        json={"case_id": case_id, "query": "unique keyword", "top_k": 20, "filters": {"type": None}},
    )
    assert qr.status_code == 200
    data = qr.json()
    assert set(data["sources"]) == {"int-md-0", "int-md-1"}


@pytest.mark.integration
def test_integration_cross_case_query_isolation(client, rag_isolation) -> None:
    for cid, did, kw in (
        ("case-A", "doc-A", "aluminum"),
        ("case-B", "doc-B", "beryllium"),
    ):
        doc = Document(
            case_id=cid,
            doc_id=did,
            raw_text=f"This matter concerns {kw} exclusively.",
            source="web",
            timestamp="2025-01-01T00:00:00+00:00",
        )
        st = StructuredDocument(
            doc_id=did,
            case_id=cid,
            summary=SummaryBlock(text=f"about {kw}", confidence=1.0),
            jurisdiction=JurisdictionBlock(),
        )
        client.post("/ingest", json={"document": doc.model_dump(), "structured": st.model_dump()})

    qa = client.post(
        "/query",
        json={"case_id": "case-A", "query": "aluminum", "top_k": 10, "filters": {"type": None}},
    )
    assert qa.status_code == 200
    for ch in qa.json()["chunks"]:
        assert ch["doc_id"] == "doc-A"

    qb = client.post(
        "/query",
        json={"case_id": "case-B", "query": "beryllium", "top_k": 10, "filters": {"type": None}},
    )
    assert qb.status_code == 200
    assert len(qb.json()["chunks"]) >= 1
    for ch in qb.json()["chunks"]:
        assert ch["doc_id"] == "doc-B"


@pytest.mark.integration
@pytest.mark.parametrize(
    "ftype,expect_substr",
    [
        ("summary", "Summary"),
        ("event", "hearing"),
        ("claim", "fraud"),
    ],
)
def test_integration_query_type_filters(client, rag_isolation, ftype: str, expect_substr: str) -> None:
    case_id = "int-filter"
    doc = Document(
        case_id=case_id,
        doc_id="int-f-1",
        raw_text="Unrelated raw filler " * 5,
        source="upload",
        timestamp="2025-01-01T00:00:00+00:00",
    )
    structured = StructuredDocument(
        doc_id="int-f-1",
        case_id=case_id,
        summary=SummaryBlock(text="Summary overview for the judge.", confidence=0.9),
        jurisdiction=JurisdictionBlock(),
        events=[Event(event="hearing scheduled", date=None, confidence=0.8, source_span="hearing")],
        claims=[Claim(type="fraud", confidence=0.7, source_span="fraud")],
    )
    assert client.post("/ingest", json={"document": doc.model_dump(), "structured": structured.model_dump()}).status_code == 200

    qr = client.post(
        "/query",
        json={"case_id": case_id, "query": expect_substr.lower(), "top_k": 5, "filters": {"type": ftype}},
    )
    assert qr.status_code == 200
    chunks = qr.json()["chunks"]
    assert len(chunks) >= 1
    for ch in chunks:
        assert ch["metadata"]["type"] == ftype


@pytest.mark.integration
def test_integration_structured_hits_match_summary_event_claim(client, rag_isolation) -> None:
    case_id = "int-sh"
    doc = Document(
        case_id=case_id,
        doc_id="int-sh-1",
        raw_text="noise",
        source="upload",
        timestamp="2025-01-01T00:00:00+00:00",
    )
    structured = StructuredDocument(
        doc_id="int-sh-1",
        case_id=case_id,
        summary=SummaryBlock(text="S-only", confidence=1.0),
        jurisdiction=JurisdictionBlock(),
        events=[Event(event="E1", date=None, confidence=1.0, source_span="noise")],
        claims=[Claim(type="C1", confidence=1.0, source_span="noise")],
    )
    client.post("/ingest", json={"document": doc.model_dump(), "structured": structured.model_dump()})
    qr = client.post(
        "/query",
        json={"case_id": case_id, "query": "S-only E1 C1", "top_k": 10, "filters": {"type": None}},
    )
    assert qr.status_code == 200
    sh = qr.json()["structured_hits"]
    types = {h["type"] for h in sh}
    assert "summary" in types
    assert "event" in types
    assert "claim" in types
    for h in sh:
        assert h["doc_id"] == "int-sh-1"
        assert 0.0 <= h["confidence"] <= 1.0


@pytest.mark.integration
@patch("rag.router.parse_legal_structure")
def test_integration_store_writes_raw_document_and_ingests(mock_parse, client, rag_isolation) -> None:
    cases_root: Path = rag_isolation["cases"]
    mock_parse.return_value = StructuredDocument(
        doc_id="placeholder",
        case_id="int-store",
        summary=SummaryBlock(text="Stored via mock.", confidence=1.0),
        jurisdiction=JurisdictionBlock(),
    )
    r = client.post(
        "/store",
        json={
            "case_id": "int-store",
            "raw_text": "Filed in district court regarding Omega.",
            "source": "upload",
            "timestamp": "2025-03-15T10:00:00+00:00",
        },
    )
    assert r.status_code == 200
    doc_id = r.json()["doc_id"]
    mock_parse.assert_called_once()
    raw_path = cases_root / "int-store" / "documents" / f"{doc_id}.txt"
    assert raw_path.read_text(encoding="utf-8") == "Filed in district court regarding Omega."
    assert (cases_root / "int-store" / "structured" / f"{doc_id}.json").exists()
    assert _chroma_count_doc(doc_id) == r.json()["num_chunks"]


@pytest.mark.integration
def test_integration_duplicate_events_deduped_to_one_event_chunk(client, rag_isolation) -> None:
    import rag.vector_store as vector_store

    case_id = "int-dedupe"
    doc_id = "int-dedupe-1"
    doc = Document(
        case_id=case_id,
        doc_id=doc_id,
        raw_text="body",
        source="upload",
        timestamp="2025-01-01T00:00:00+00:00",
    )
    structured = StructuredDocument(
        doc_id=doc_id,
        case_id=case_id,
        summary=SummaryBlock(text="", confidence=0.0),
        jurisdiction=JurisdictionBlock(),
        events=[
            Event(event="Same day hearing", date=None, confidence=0.9, source_span="body"),
            Event(event="same day hearing", date=None, confidence=0.8, source_span="body"),
        ],
    )
    assert client.post("/ingest", json={"document": doc.model_dump(), "structured": structured.model_dump()}).status_code == 200
    col = vector_store.get_collection()
    res = col.get(where={"$and": [{"doc_id": doc_id}, {"type": "event"}]})
    assert len(res.get("ids") or []) == 1


@pytest.mark.integration
def test_integration_empty_summary_skips_summary_chunk_but_raw_remains(client, rag_isolation) -> None:
    case_id = "int-ns"
    doc = Document(
        case_id=case_id,
        doc_id="int-ns-1",
        raw_text="Still have raw content here.",
        source="upload",
        timestamp="2025-01-01T00:00:00+00:00",
    )
    structured = StructuredDocument(
        doc_id="int-ns-1",
        case_id=case_id,
        summary=SummaryBlock(text="", confidence=0.0),
        jurisdiction=JurisdictionBlock(),
    )
    r = client.post("/ingest", json={"document": doc.model_dump(), "structured": structured.model_dump()})
    assert r.status_code == 200
    qr = client.post(
        "/query",
        json={"case_id": case_id, "query": "raw content", "top_k": 5, "filters": {"type": "summary"}},
    )
    assert qr.json()["chunks"] == []
