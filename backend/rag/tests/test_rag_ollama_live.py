"""
Optional end-to-end tests against a real Ollama server (127.0.0.1:11434).
Skipped automatically when Ollama is down or the model is missing.

Run only these:
  pytest rag/tests/test_rag_ollama_live.py -m ollama -v
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from main import app
from schemas import Document


@pytest.fixture
def client(rag_isolation):
    return TestClient(app)


@pytest.mark.ollama
def test_live_parse_returns_valid_structured_document(require_ollama, client, rag_isolation) -> None:
    """Calls real Ollama via parser.parse_legal_structure; model from OLLAMA_MODEL env."""
    doc = Document(
        case_id="live-parse-case",
        doc_id="live-parse-doc",
        raw_text=(
            "Plaintiff Jane Roe sued defendant Acme Inc. on March 1, 2025 "
            "for breach of contract. The complaint seeks $50,000 in damages."
        ),
        source="upload",
        timestamp="2025-03-01T12:00:00+00:00",
    )
    r = client.post("/parse", json=doc.model_dump())
    if r.status_code != 200:
        try:
            detail = r.json()
        except Exception:
            detail = r.text
        pytest.skip(f"Ollama parse not available: {r.status_code} {detail}")
    data = r.json()
    assert data["case_id"] == "live-parse-case"
    assert data["doc_id"] == "live-parse-doc"
    assert "summary" in data and "text" in data["summary"]
    assert isinstance(data.get("events"), list)
    assert isinstance(data.get("claims"), list)


@pytest.mark.ollama
def test_live_store_parses_and_query_returns_chunks(require_ollama, client, rag_isolation) -> None:
    """Full /store (parse + ingest + disk) then /query; skips if model errors."""
    case_id = "live-store-case"
    r = client.post(
        "/store",
        json={
            "case_id": case_id,
            "raw_text": (
                "Motion to dismiss filed by Beta LLC on April 2, 2025. "
                "Plaintiff Alpha Corp alleges trademark infringement."
            ),
            "source": "upload",
            "timestamp": "2025-04-02T15:00:00+00:00",
        },
    )
    if r.status_code != 200:
        pytest.skip(f"Ollama store pipeline failed: {r.status_code} {r.text}")
    doc_id = r.json()["doc_id"]
    qr = client.post(
        "/query",
        json={
            "case_id": case_id,
            "query": "trademark infringement motion",
            "top_k": 5,
            "filters": {"type": None},
        },
    )
    assert qr.status_code == 200
    body = qr.json()
    assert doc_id in body["sources"]
    assert len(body["chunks"]) >= 1
