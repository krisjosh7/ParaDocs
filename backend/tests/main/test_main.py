from __future__ import annotations

from unittest.mock import patch

from fastapi.testclient import TestClient

from main import app, cleanup_session_media


def test_health() -> None:
    client = TestClient(app)
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}


@patch("main.shutil.rmtree")
def test_cleanup_session_media(mock_rmtree) -> None:
    cleanup_session_media()
    mock_rmtree.assert_called()


def test_echo() -> None:
    client = TestClient(app)
    r = client.post("/echo", json={"a": 1, "b": [2, 3]})
    assert r.status_code == 200
    assert r.json() == {"a": 1, "b": [2, 3]}
