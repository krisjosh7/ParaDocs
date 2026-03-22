from __future__ import annotations

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


@pytest.fixture
def client(rag_isolation):
    return TestClient(app)


def _sample_structured(doc_id: str, case_id: str) -> StructuredDocument:
    return StructuredDocument(
        doc_id=doc_id,
        case_id=case_id,
        summary=SummaryBlock(text="Alice sued Bob.", confidence=0.8),
        jurisdiction=JurisdictionBlock(),
        events=[
            Event(
                event="filing",
                date="2024-01-01",
                confidence=0.9,
                source_span="Alice sued Bob",
            )
        ],
        claims=[Claim(type="negligence", confidence=0.7, source_span="negligence")],
    )


def test_ingest_returns_num_chunks_and_doc_id(client) -> None:
    doc = Document(
        case_id="case-ut",
        doc_id="doc-ut-1",
        raw_text="Alice sued Bob for negligence on 2024-01-01.\n\nDamages alleged.",
        source="upload",
        timestamp="2024-01-15T00:00:00+00:00",
    )
    structured = _sample_structured("doc-ut-1", "case-ut")
    r = client.post("/ingest", json={"document": doc.model_dump(), "structured": structured.model_dump()})
    assert r.status_code == 200
    body = r.json()
    assert body["doc_id"] == "doc-ut-1"
    assert body["num_chunks"] >= 1


def test_query_returns_query_echo_and_chunk_shape(client) -> None:
    doc = Document(
        case_id="case-ut2",
        doc_id="doc-ut-2",
        raw_text="Charlie sued Delta Corp for breach.",
        source="upload",
        timestamp="2024-01-15T00:00:00+00:00",
    )
    structured = StructuredDocument(
        doc_id="doc-ut-2",
        case_id="case-ut2",
        summary=SummaryBlock(text="Breach case.", confidence=0.8),
        jurisdiction=JurisdictionBlock(),
    )
    ir = client.post("/ingest", json={"document": doc.model_dump(), "structured": structured.model_dump()})
    assert ir.status_code == 200

    qr = client.post(
        "/query",
        json={
            "case_id": "case-ut2",
            "query": "breach",
            "top_k": 5,
            "filters": {"type": None},
        },
    )
    assert qr.status_code == 200
    data = qr.json()
    assert data["query"] == "breach"
    assert "chunks" in data
    assert "structured_hits" in data
    assert "sources" in data
    if data["chunks"]:
        c0 = data["chunks"][0]
        assert "chunk_id" in c0 and "text" in c0 and "metadata" in c0
        assert "type" in c0["metadata"]


def test_query_filter_raw_only(client) -> None:
    doc = Document(
        case_id="case-ut3",
        doc_id="doc-ut-3",
        raw_text="Only raw text here.\n\nSecond block.",
        source="upload",
        timestamp="2024-01-15T00:00:00+00:00",
    )
    structured = StructuredDocument(
        doc_id="doc-ut-3",
        case_id="case-ut3",
        summary=SummaryBlock(text="Summary line.", confidence=1.0),
        jurisdiction=JurisdictionBlock(),
    )
    client.post("/ingest", json={"document": doc.model_dump(), "structured": structured.model_dump()})
    qr = client.post(
        "/query",
        json={
            "case_id": "case-ut3",
            "query": "text",
            "top_k": 10,
            "filters": {"type": "raw"},
        },
    )
    assert qr.status_code == 200
    for ch in qr.json()["chunks"]:
        assert ch["metadata"]["type"] == "raw"


@patch("rag.router.parse_legal_structure")
def test_parse_endpoint_delegates(mock_parse, client, rag_isolation):
    mock_parse.return_value = StructuredDocument(
        doc_id="doc-pe",
        case_id="case-pe",
        summary=SummaryBlock(text="via parse", confidence=1.0),
        jurisdiction=JurisdictionBlock(),
    )
    r = client.post(
        "/parse",
        json={
            "case_id": "case-pe",
            "doc_id": "doc-pe",
            "raw_text": "body",
            "source": "upload",
            "timestamp": "2024-01-01T00:00:00+00:00",
        },
    )
    assert r.status_code == 200
    assert r.json()["summary"]["text"] == "via parse"
    mock_parse.assert_called_once()


@patch("rag.router.parse_legal_structure")
def test_store_flow(mock_parse, client, rag_isolation):
    mock_parse.return_value = StructuredDocument(
        doc_id="ignored",
        case_id="case-st",
        summary=SummaryBlock(text="stub summary", confidence=1.0),
        jurisdiction=JurisdictionBlock(),
    )
    r = client.post(
        "/store",
        json={
            "case_id": "case-st",
            "raw_text": "Some raw content for store.",
            "source": "upload",
        },
    )
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "stored"
    assert body["summary"] == "stub summary"
    assert "doc_id" in body
    mock_parse.assert_called_once()
