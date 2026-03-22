"""
Resolve RAG doc_id → Context Library row or on-disk metadata for timeline UI.
"""

from __future__ import annotations

import json
from typing import Any

from context_catalog import read_catalog
from storage import default_cases_root


def resolve_timeline_source(case_id: str, doc_id: str | None) -> dict[str, Any]:
    """
    Best-effort provenance for an event extracted from a structured document.
    Context Library items store the same UUID on `rag_doc_id` as events' `doc_id`.
    """
    if doc_id is None or not str(doc_id).strip():
        return {
            "kind": "unknown",
            "label": "Source not linked",
            "rag_doc_id": None,
        }
    did = str(doc_id).strip()

    for row in read_catalog(case_id):
        if str(row.get("rag_doc_id") or "").strip() == did:
            title = (row.get("title") or "").strip() or "Untitled context"
            return {
                "kind": "context_library",
                "label": title,
                "context_id": row.get("id"),
                "title": title,
                "type": row.get("type"),
                "added_at": row.get("added_at"),
                "source_url": row.get("source_url"),
                "file_name": row.get("file_name"),
                "caption": (row.get("caption") or "").strip() or None,
                "rag_doc_id": did,
            }

    meta_path = default_cases_root() / case_id / "metadata" / f"{did}.json"
    if meta_path.is_file():
        try:
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            meta = {}
        if isinstance(meta, dict):
            src = meta.get("source") or "upload"
            ts = meta.get("timestamp")
            url = meta.get("source_url")
            return {
                "kind": "ingested_document",
                "label": f"Ingested document ({src})",
                "rag_doc_id": did,
                "ingest_source": str(src) if src else None,
                "timestamp": str(ts) if ts else None,
                "source_url": str(url).strip() if isinstance(url, str) and url.strip() else None,
            }

    return {
        "kind": "ingested_document",
        "label": f"Document {did[:8]}…" if len(did) > 8 else f"Document {did}",
        "rag_doc_id": did,
    }
