from __future__ import annotations

import os

import pytest


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
