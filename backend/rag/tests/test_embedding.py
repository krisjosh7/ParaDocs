from __future__ import annotations

from unittest.mock import MagicMock

import pytest

import rag.embedding as embedding


@pytest.fixture(autouse=True)
def reset_embedding_module():
    embedding._EMBEDDING_MODEL_UNAVAILABLE = False
    embedding.get_embedder.cache_clear()
    yield
    embedding._EMBEDDING_MODEL_UNAVAILABLE = False
    embedding.get_embedder.cache_clear()


def test_get_embedder_uses_sentence_transformers(monkeypatch) -> None:
    mock_model = MagicMock()
    mock_cls = MagicMock(return_value=mock_model)
    monkeypatch.setattr(embedding, "SentenceTransformer", mock_cls)
    embedding.get_embedder.cache_clear()
    m = embedding.get_embedder()
    assert m is mock_model
    mock_cls.assert_called_once()
    embedding.get_embedder.cache_clear()


def test_embed_texts_empty() -> None:
    assert embedding.embed_texts([]) == []


def test_hash_embedding_empty_and_words() -> None:
    z = embedding._hash_embedding("")
    assert len(z) == 384
    assert sum(abs(x) for x in z) == 0.0
    v = embedding._hash_embedding("hello world")
    assert len(v) == 384
    nrm = sum(x * x for x in v) ** 0.5
    assert nrm == pytest.approx(1.0)


def test_embed_texts_success_path(monkeypatch) -> None:
    fake = type("M", (), {})()
    import numpy as np

    fake.encode = lambda texts, normalize_embeddings=True: np.array([[0.25, 0.25, 0.5, 0.0]])

    embedding.get_embedder.cache_clear()
    embedding._EMBEDDING_MODEL_UNAVAILABLE = False
    monkeypatch.setattr(embedding, "get_embedder", lambda: fake)
    out = embedding.embed_texts(["one"])
    assert len(out) == 1
    assert len(out[0]) == 4
    assert out[0][0] == pytest.approx(0.25)


def test_embed_texts_fallback_on_model_failure(monkeypatch) -> None:
    def boom():
        raise RuntimeError("model unavailable")

    monkeypatch.setattr(embedding, "get_embedder", boom)
    vecs = embedding.embed_texts(["alpha", "beta"])
    assert len(vecs) == 2
    assert len(vecs[0]) == 384
    assert embedding._EMBEDDING_MODEL_UNAVAILABLE is True
    vecs2 = embedding.embed_texts(["gamma"])
    assert len(vecs2) == 1
    assert len(vecs2[0]) == 384
