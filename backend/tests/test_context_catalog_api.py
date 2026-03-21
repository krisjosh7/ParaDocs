from __future__ import annotations

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
