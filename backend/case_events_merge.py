"""
Merge per-document structured events into cases/{case_id}/events.json.

Used by:
- ingest_endpoint (every RAG ingest, including Discovery via store_document_for_rag)
- normalize_events_node (LangGraph Phase 1 graph)

Lives at backend root (not under workflow/) so rag/router can import without
loading workflow/__init__.py (which would circular-import rag.router).
"""

from __future__ import annotations

import json
from pathlib import Path

from schemas import StructuredDocument
from storage import default_cases_root


def _dedupe_key(ev: dict) -> tuple[str, str]:
    return (
        (ev.get("event") or "").strip().lower(),
        (ev.get("source_span") or "").strip(),
    )


def _sort_key(ev: dict) -> tuple[int, str]:
    """Events with a date sort first (chronologically); nulls/empty sort last."""
    date = (ev.get("date") or "").strip()
    if date:
        return (0, date)
    return (1, "")


def _read_existing_events(path: Path) -> list[dict]:
    if not path.is_file():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return []
    if not isinstance(data, list):
        return []
    return [e for e in data if isinstance(e, dict)]


def _merge_and_dedupe(existing: list[dict], new: list[dict]) -> list[dict]:
    seen: set[tuple[str, str]] = set()
    merged: list[dict] = []
    for ev in existing + new:
        text = (ev.get("event") or "").strip()
        if not text:
            continue
        key = _dedupe_key(ev)
        if key in seen:
            continue
        seen.add(key)
        merged.append(ev)
    merged.sort(key=_sort_key)
    return merged


def events_dicts_from_structured(structured: StructuredDocument, doc_id: str) -> list[dict]:
    """StructuredDocument.events as dicts with doc_id provenance."""
    out: list[dict] = []
    for ev in structured.events:
        d = ev.model_dump()
        d["doc_id"] = doc_id
        out.append(d)
    return out


def merge_new_events_into_case_file(case_id: str, new_events: list[dict]) -> list[dict]:
    """
    Read cases/{case_id}/events.json if present, merge + dedupe + sort, write back.
    Returns the full normalized list for callers that need state updates.
    """
    events_path = default_cases_root() / case_id / "events.json"
    events_path.parent.mkdir(parents=True, exist_ok=True)

    existing = _read_existing_events(events_path)
    normalized = _merge_and_dedupe(existing, new_events)
    events_path.write_text(json.dumps(normalized, indent=2), encoding="utf-8")
    return normalized


def append_events_from_ingest(
    case_id: str,
    doc_id: str,
    structured: StructuredDocument,
) -> list[dict]:
    """
    After structured JSON is written for a doc, merge its events into the case events index.
    Idempotent for same (event, source_span) across re-ingest of the same text.
    """
    new = events_dicts_from_structured(structured, doc_id)
    return merge_new_events_into_case_file(case_id, new)
