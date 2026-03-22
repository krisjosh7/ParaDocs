from __future__ import annotations

import json
from pathlib import Path

import pytest

from timeline_provenance import resolve_timeline_source


def test_resolve_unknown_without_doc_id() -> None:
    r = resolve_timeline_source("case-x", None)
    assert r["kind"] == "unknown"


def test_resolve_context_library_match(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CASES_ROOT", str(tmp_path))
    cid = "case-y"
    base = tmp_path / cid / "contexts"
    base.mkdir(parents=True)
    catalog = [
        {
            "id": "ctx-1",
            "title": "My memo",
            "type": "text",
            "rag_doc_id": "rag-uuid-123",
        }
    ]
    (base / "catalog.json").write_text(json.dumps(catalog), encoding="utf-8")

    r = resolve_timeline_source(cid, "rag-uuid-123")
    assert r["kind"] == "context_library"
    assert r["title"] == "My memo"
    assert r["context_id"] == "ctx-1"
