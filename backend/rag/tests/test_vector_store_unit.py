from __future__ import annotations

from unittest.mock import MagicMock

import rag.vector_store as vector_store


def test_distance_to_score() -> None:
    assert vector_store._distance_to_score(None) == 0.0
    assert vector_store._distance_to_score(0) == 1.0
    assert vector_store._distance_to_score(1) == 0.0
    assert vector_store._distance_to_score(2) == 0.0
    assert vector_store._distance_to_score(-1) == 1.0


def test_chroma_metadata_none_values() -> None:
    assert vector_store._chroma_metadata({"a": None, "b": 1}) == {"a": "", "b": 1}


def test_upsert_text_records_empty() -> None:
    assert vector_store.upsert_text_records([]) == 0


def test_delete_chunks_for_doc_id_blank() -> None:
    vector_store.delete_chunks_for_doc_id("")
    vector_store.delete_chunks_for_doc_id("   ")


def test_delete_chunks_swallows_delete_error(monkeypatch) -> None:
    coll = MagicMock()
    coll.delete.side_effect = RuntimeError("chromadb error")
    monkeypatch.setattr(vector_store, "get_collection", lambda: coll)
    vector_store.delete_chunks_for_doc_id("any-id")


def test_get_collection_default_persist_dir(monkeypatch) -> None:
    """Cover branch when CHROMA_PERSIST_DIR is unset (uses backend/chroma)."""
    monkeypatch.delenv("CHROMA_PERSIST_DIR", raising=False)
    vector_store.get_collection.cache_clear()
    col = vector_store.get_collection()
    assert col.name == "case_documents"
    vector_store.get_collection.cache_clear()
