"""Chroma persistent client + collection access without loading embedding models."""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path

import chromadb
from chromadb.api.models.Collection import Collection

COLLECTION_NAME = "case_documents"


def _backend_root() -> Path:
    """backend/ directory (parent of the rag package)."""
    return Path(__file__).resolve().parent.parent


@lru_cache(maxsize=1)
def get_collection() -> Collection:
    persist_dir = os.environ.get("CHROMA_PERSIST_DIR", "").strip()
    if not persist_dir:
        persist_dir = str((_backend_root() / "chroma").resolve())
    client = chromadb.PersistentClient(path=persist_dir)
    return client.get_or_create_collection(name=COLLECTION_NAME, metadata={"hnsw:space": "cosine"})


def delete_chunks_for_doc_id(doc_id: str) -> None:
    """Remove all vector rows for a document so re-ingest does not leave orphans or duplicates."""
    if not doc_id.strip():
        return
    collection = get_collection()
    try:
        collection.delete(where={"doc_id": doc_id})
    except Exception:
        # Older Chroma / empty collection: best-effort
        pass
