from __future__ import annotations

import os
import urllib.error
import urllib.request

import pytest


def ollama_server_reachable(timeout_s: float = 1.5) -> bool:
    try:
        req = urllib.request.Request(
            "http://127.0.0.1:11434/api/tags",
            method="GET",
            headers={"Accept": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=timeout_s) as resp:
            return resp.status == 200
    except (OSError, urllib.error.URLError, TimeoutError):
        return False


@pytest.fixture
def require_ollama() -> None:
    if not ollama_server_reachable():
        pytest.skip("Ollama not reachable at http://127.0.0.1:11434")


@pytest.fixture
def rag_isolation(monkeypatch, tmp_path):
    """Fresh Chroma + cases dirs per test; deterministic fake embeddings."""
    chroma_dir = tmp_path / "chroma_test"
    cases_dir = tmp_path / "cases_test"
    chroma_dir.mkdir()
    cases_dir.mkdir()
    monkeypatch.setenv("CHROMA_PERSIST_DIR", str(chroma_dir))
    monkeypatch.setenv("CASES_ROOT", str(cases_dir))

    import vector_store

    vector_store.get_collection.cache_clear()

    def fake_embed_texts(texts: list[str]) -> list[list[float]]:
        dim = 8
        out: list[list[float]] = []
        for j, _ in enumerate(texts):
            vec = [0.0] * dim
            vec[j % dim] = 1.0
            out.append(vec)
        return out

    monkeypatch.setattr(vector_store, "embed_texts", fake_embed_texts)
    yield {"chroma": chroma_dir, "cases": cases_dir}
    vector_store.get_collection.cache_clear()
