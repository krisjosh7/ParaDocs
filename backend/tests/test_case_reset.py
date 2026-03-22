from __future__ import annotations

import json
from pathlib import Path

import pytest

from case_reset import reset_case_context_timeline_and_rag


@pytest.fixture()
def cases_root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    root = tmp_path / "cases_data"
    root.mkdir()
    monkeypatch.setenv("CASES_ROOT", str(root))
    return root


def test_reset_clears_context_events_timeline_and_docs(
    cases_root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    deleted: list[str] = []

    def _capture(did: str) -> None:
        deleted.append(did)

    case_id = "case-reset-1"
    base = cases_root / case_id
    (base / "contexts" / "files").mkdir(parents=True)
    (base / "contexts" / "catalog.json").write_text(
        json.dumps([{"id": "ctx-1", "rag_doc_id": "doc-from-catalog"}]),
        encoding="utf-8",
    )
    (base / "metadata").mkdir(parents=True)
    (base / "documents").mkdir(parents=True)
    (base / "metadata" / "doc-meta-only.json").write_text("{}", encoding="utf-8")
    (base / "documents" / "doc-meta-only.txt").write_text("hello", encoding="utf-8")

    reset_case_context_timeline_and_rag(case_id, delete_chunks_for_doc_id=_capture)

    assert json.loads((base / "contexts" / "catalog.json").read_text(encoding="utf-8")) == []
    assert json.loads((base / "events.json").read_text(encoding="utf-8")) == []
    assert (base / "timelines.json").is_file()
    tl = json.loads((base / "timelines.json").read_text(encoding="utf-8"))
    assert tl["case_id"] == case_id
    assert tl["primary"]["entries"] == []
    assert not (base / "documents" / "doc-meta-only.txt").is_file()
    assert not (base / "metadata" / "doc-meta-only.json").is_file()
    assert set(deleted) == {"doc-from-catalog", "doc-meta-only"}
