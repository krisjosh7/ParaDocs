from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from main import app


@pytest.fixture()
def cases_root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    root = tmp_path / "cases_data"
    root.mkdir()
    monkeypatch.setenv("CASES_ROOT", str(root))
    return root


@pytest.fixture()
def client(cases_root: Path) -> TestClient:
    return TestClient(app)


def test_discovered_empty(client: TestClient) -> None:
    r = client.get("/cases/case-a/discovered-documents")
    assert r.status_code == 200
    assert r.json() == {"items": []}


def test_discovered_lists_metadata_and_structured(client: TestClient, cases_root: Path) -> None:
    base = cases_root / "case-a"
    (base / "metadata").mkdir(parents=True)
    (base / "structured").mkdir(parents=True)
    (base / "documents").mkdir(parents=True)
    meta = {
        "case_id": "case-a",
        "doc_id": "doc-1",
        "source": "web",
        "timestamp": "2026-01-02T00:00:00+00:00",
        "status": "ingested",
    }
    structured = {"doc_id": "doc-1", "summary": {"text": "Hello", "confidence": 0.9}}
    (base / "metadata" / "doc-1.json").write_text(json.dumps(meta), encoding="utf-8")
    (base / "structured" / "doc-1.json").write_text(json.dumps(structured), encoding="utf-8")
    (base / "documents" / "doc-1.txt").write_text(
        "Title\nSource: https://example.com/opinion/123\n\nBody",
        encoding="utf-8",
    )

    r = client.get("/cases/case-a/discovered-documents")
    assert r.status_code == 200
    data = r.json()
    assert len(data["items"]) == 1
    assert data["items"][0]["doc_id"] == "doc-1"
    assert data["items"][0]["metadata"]["source"] == "web"
    assert data["items"][0]["structured"]["summary"]["text"] == "Hello"
    assert data["items"][0]["sourceUrl"] == "https://example.com/opinion/123"


def test_discovered_invalid_case_id(client: TestClient) -> None:
    r = client.get("/cases/not%20valid/discovered-documents")
    assert r.status_code == 400


def test_delete_discovered_document(
    client: TestClient, cases_root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    chunks_removed: list[str] = []

    def _fake_delete(doc_id: str) -> None:
        chunks_removed.append(doc_id)

    monkeypatch.setattr("routes_discovered.delete_chunks_for_doc_id", _fake_delete)

    base = cases_root / "case-a"
    for sub in ("metadata", "structured", "documents"):
        (base / sub).mkdir(parents=True)
    (base / "metadata" / "doc-1.json").write_text("{}", encoding="utf-8")
    (base / "structured" / "doc-1.json").write_text("{}", encoding="utf-8")
    (base / "documents" / "doc-1.txt").write_text("x", encoding="utf-8")

    r = client.delete("/cases/case-a/discovered-documents/doc-1")
    assert r.status_code == 200
    assert r.json() == {"status": "deleted", "id": "doc-1"}
    assert chunks_removed == ["doc-1"]
    assert not (base / "metadata" / "doc-1.json").is_file()
    assert not (base / "structured" / "doc-1.json").is_file()
    assert not (base / "documents" / "doc-1.txt").is_file()


def test_delete_discovered_idempotent_missing_meta(client: TestClient, cases_root: Path) -> None:
    """No metadata file (e.g. already removed by catalog cascade) still returns success."""
    (cases_root / "case-a" / "metadata").mkdir(parents=True)
    r = client.delete("/cases/case-a/discovered-documents/unknown-doc")
    assert r.status_code == 200
    assert r.json() == {"status": "deleted", "id": "unknown-doc"}
