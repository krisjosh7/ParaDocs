from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from case_events_merge import parse_context_id_from_discovery_header
from main import app


@pytest.fixture(autouse=True)
def _no_background_rag(monkeypatch: pytest.MonkeyPatch) -> None:
    """Avoid Ollama/Chroma during context API tests (patch where the task is referenced)."""
    monkeypatch.setattr(
        "routes_contexts.background_ingest_context_to_rag",
        lambda *args, **kwargs: None,
    )


@pytest.fixture()
def cases_root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    root = tmp_path / "cases_data"
    root.mkdir()
    monkeypatch.setenv("CASES_ROOT", str(root))
    return root


@pytest.fixture()
def client(cases_root: Path) -> TestClient:
    return TestClient(app)


def test_parse_context_id_from_discovery_header() -> None:
    raw = "[Discovery context | case_id=case-a | context_id=ctx-test123]\nTitle: T\n\nbody"
    assert parse_context_id_from_discovery_header(raw) == "ctx-test123"


def test_list_empty(client: TestClient) -> None:
    r = client.get("/cases/case-a/contexts")
    assert r.status_code == 200
    assert r.json() == {"items": []}


def test_create_text_and_list_filter(client: TestClient, cases_root: Path) -> None:
    r = client.post(
        "/cases/case-a/contexts",
        data={
            "context_type": "text",
            "title": "Note one",
            "caption": "cap",
            "text_full": "alpha beta uniqueword",
        },
    )
    assert r.status_code == 200
    data = r.json()
    assert data["type"] == "text"
    assert data["title"] == "Note one"
    assert "uniqueword" in (data.get("textFull") or "")

    cat = cases_root / "case-a" / "contexts" / "catalog.json"
    assert cat.is_file()

    r2 = client.get("/cases/case-a/contexts")
    assert len(r2.json()["items"]) == 1

    r3 = client.get("/cases/case-a/contexts", params={"q": "uniqueword"})
    assert len(r3.json()["items"]) == 1

    r4 = client.get("/cases/case-a/contexts", params={"q": "nomatch"})
    assert r4.json()["items"] == []


def test_create_file_and_media(client: TestClient, cases_root: Path) -> None:
    files = {"file": ("hello.png", b"\x89PNG\r\n\x1a\n", "image/png")}
    r = client.post(
        "/cases/case-b/contexts",
        data={
            "context_type": "image",
            "title": "Pic",
            "caption": "",
            "doc_subtype": "",
        },
        files=files,
    )
    assert r.status_code == 200
    body = r.json()
    assert body["type"] == "image"
    assert body.get("imageSrc")

    item_id = body["id"]
    media = client.get(f"/cases/case-b/contexts/{item_id}/media")
    assert media.status_code == 200
    assert media.content.startswith(b"\x89PNG")


def test_delete_item(client: TestClient) -> None:
    client.post(
        "/cases/case-c/contexts",
        data={"context_type": "text", "title": "T", "text_full": "x"},
    )
    lst = client.get("/cases/case-c/contexts").json()["items"]
    iid = lst[0]["id"]
    d = client.delete(f"/cases/case-c/contexts/{iid}")
    assert d.status_code == 200
    assert client.get("/cases/case-c/contexts").json()["items"] == []


def test_remove_events_for_doc_id(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CASES_ROOT", str(tmp_path))
    case_id = "cev-case"
    base = tmp_path / case_id
    base.mkdir(parents=True)
    events = [
        {"event": "A", "doc_id": "d-keep", "source_span": "1", "date": "2024-01-02"},
        {"event": "B", "doc_id": "d-drop", "source_span": "2", "date": "2024-01-01"},
    ]
    (base / "events.json").write_text(json.dumps(events), encoding="utf-8")

    from case_events_merge import remove_events_for_doc_id

    assert remove_events_for_doc_id(case_id, "d-drop") == 1
    left = json.loads((base / "events.json").read_text(encoding="utf-8"))
    assert len(left) == 1
    assert left[0]["doc_id"] == "d-keep"


def test_delete_cascades_rag_doc_id(
    client: TestClient, cases_root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Deleting a context row with rag_doc_id removes Chroma + documents/structured/metadata for that id."""
    deleted_chunks: list[str] = []

    def _capture_delete(doc_id: str) -> None:
        deleted_chunks.append(doc_id)

    monkeypatch.setattr("rag.vector_store.delete_chunks_for_doc_id", _capture_delete)
    monkeypatch.setattr("timeline_logic.rebuild_case_timeline", lambda _cid: None)

    from context_catalog import write_catalog

    case_id = "case-rag-cascade"
    rag_id = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
    row = {
        "id": "ctx-rag-1",
        "type": "text",
        "title": "T",
        "caption": "",
        "added_at": "2020-01-01T00:00:00+00:00",
        "file_name": None,
        "stored_file": None,
        "text_full": "hello",
        "doc_subtype": None,
        "rag_doc_id": rag_id,
    }
    write_catalog(case_id, [row])

    base = cases_root / case_id
    for sub in ("documents", "structured", "metadata"):
        (base / sub).mkdir(parents=True, exist_ok=True)
    (base / "documents" / f"{rag_id}.txt").write_text("raw", encoding="utf-8")
    (base / "structured" / f"{rag_id}.json").write_text("{}", encoding="utf-8")
    (base / "metadata" / f"{rag_id}.json").write_text("{}", encoding="utf-8")
    ev = [{"event": "From deleted doc", "doc_id": rag_id, "source_span": "x", "date": "2024-06-01"}]
    (base / "events.json").write_text(json.dumps(ev), encoding="utf-8")

    r = client.delete(f"/cases/{case_id}/contexts/ctx-rag-1")
    assert r.status_code == 200
    assert deleted_chunks == [rag_id]
    assert not (base / "documents" / f"{rag_id}.txt").is_file()
    assert not (base / "structured" / f"{rag_id}.json").is_file()
    assert not (base / "metadata" / f"{rag_id}.json").is_file()
    assert (base / "events.json").read_text(encoding="utf-8").strip() == "[]"


def test_remove_events_for_context_id(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CASES_ROOT", str(tmp_path))
    case_id = "cev-ctx"
    base = tmp_path / case_id
    base.mkdir(parents=True)
    events = [
        {"event": "Keep", "doc_id": "d1", "context_id": None, "source_span": "1", "date": "2024-01-02"},
        {"event": "Drop", "doc_id": "d2", "context_id": "ctx-x", "source_span": "2", "date": "2024-01-01"},
    ]
    (base / "events.json").write_text(json.dumps(events), encoding="utf-8")

    from case_events_merge import remove_events_for_context_id

    assert remove_events_for_context_id(case_id, "ctx-x") == 1
    left = json.loads((base / "events.json").read_text(encoding="utf-8"))
    assert len(left) == 1
    assert left[0]["event"] == "Keep"


def test_delete_cascades_by_context_id_without_rag_doc(
    client: TestClient, cases_root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Deleting a library row removes timeline events tagged with that context_id even when rag_doc_id is unset."""
    monkeypatch.setattr("timeline_logic.rebuild_case_timeline", lambda _cid: None)

    from context_catalog import write_catalog

    case_id = "case-ctx-only"
    row = {
        "id": "ctx-no-rag",
        "type": "text",
        "title": "Pending ingest",
        "caption": "",
        "added_at": "2020-01-01T00:00:00+00:00",
        "file_name": None,
        "stored_file": None,
        "text_full": "hello",
        "doc_subtype": None,
        "rag_doc_id": None,
    }
    write_catalog(case_id, [row])

    base = cases_root / case_id
    base.mkdir(parents=True)
    ev = [
        {
            "event": "From ctx row",
            "doc_id": "some-doc",
            "context_id": "ctx-no-rag",
            "source_span": "x",
            "date": "2024-06-01",
        }
    ]
    (base / "events.json").write_text(json.dumps(ev), encoding="utf-8")

    r = client.delete(f"/cases/{case_id}/contexts/ctx-no-rag")
    assert r.status_code == 200
    assert json.loads((base / "events.json").read_text(encoding="utf-8")) == []
