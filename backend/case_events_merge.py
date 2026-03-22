"""
Merge per-document structured events into cases/{case_id}/events.json.

Used by:
- ingest_endpoint (every RAG ingest, including Discovery via store_document_for_rag)
- normalize_events_node (LangGraph Phase 1 graph)
- routes_contexts.delete_context (remove_events_for_doc_id after catalog item removed from RAG)

Lives at backend root (not under workflow/) so rag/router can import without
loading workflow/__init__.py (which would circular-import rag.router).
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from event_date_enrichment import enrich_events_from_source_text
from schemas import StructuredDocument
from storage import default_cases_root

_CONTEXT_HEADER_RE = re.compile(
    r"\[Discovery context\s*\|\s*case_id=[^\]|]*\s*\|\s*context_id=([^\s\]]+)\]",
    re.IGNORECASE,
)


def parse_context_id_from_discovery_header(raw_text: str) -> str | None:
    """Match the header prefix written by build_raw_text_for_context_rag."""
    if not raw_text:
        return None
    m = _CONTEXT_HEADER_RE.search(raw_text[:20000])
    if not m:
        return None
    cid = m.group(1).strip()
    return cid or None


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


def remove_events_for_doc_id(case_id: str, doc_id: str) -> int:
    """
    Drop all events in cases/{case_id}/events.json that reference doc_id (e.g. after RAG doc removal).
    Returns how many events were removed. Rewrites the file only if something changed.
    """
    doc_id = (doc_id or "").strip()
    if not doc_id or ".." in doc_id or "/" in doc_id or "\\" in doc_id:
        return 0
    events_path = default_cases_root() / case_id / "events.json"
    existing = _read_existing_events(events_path)
    if not existing:
        return 0
    kept = [e for e in existing if str(e.get("doc_id") or "").strip() != doc_id]
    removed = len(existing) - len(kept)
    if removed == 0:
        return 0
    events_path.parent.mkdir(parents=True, exist_ok=True)
    events_path.write_text(json.dumps(kept, indent=2), encoding="utf-8")
    return removed


def remove_events_for_context_id(case_id: str, context_id: str) -> int:
    """
    Drop events tagged with a Discovery catalog row id (ctx-…).
    Used when deleting a library item even if rag_doc_id was never linked.
    """
    context_id = (context_id or "").strip()
    if not context_id or ".." in context_id or "/" in context_id or "\\" in context_id:
        return 0
    events_path = default_cases_root() / case_id / "events.json"
    existing = _read_existing_events(events_path)
    if not existing:
        return 0
    kept = [e for e in existing if str(e.get("context_id") or "").strip() != context_id]
    removed = len(existing) - len(kept)
    if removed == 0:
        return 0
    kept.sort(key=_sort_key)
    events_path.parent.mkdir(parents=True, exist_ok=True)
    events_path.write_text(json.dumps(kept, indent=2), encoding="utf-8")
    return removed


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
    doc_txt = default_cases_root() / case_id / "documents" / f"{doc_id}.txt"
    if doc_txt.is_file():
        try:
            raw = doc_txt.read_text(encoding="utf-8", errors="replace")
        except OSError:
            raw = ""
        if raw:
            enrich_events_from_source_text(new, raw)
            cxid = parse_context_id_from_discovery_header(raw)
            if cxid:
                for d in new:
                    d["context_id"] = cxid
    return merge_new_events_into_case_file(case_id, new)


def backfill_case_event_dates(case_id: str) -> int:
    """
    Re-read stored document text and fill missing dates on events in events.json.
    Returns how many events gained a new non-empty date.
    """
    events_path = default_cases_root() / case_id / "events.json"
    existing = _read_existing_events(events_path)
    if not existing:
        return 0
    docs_dir = default_cases_root() / case_id / "documents"
    by_doc: dict[str, list[dict]] = {}
    for ev in existing:
        did = str(ev.get("doc_id") or "").strip()
        if not did or ".." in did or "/" in did or "\\" in did:
            continue
        by_doc.setdefault(did, []).append(ev)
    changed = 0
    for did, evs in by_doc.items():
        fp = docs_dir / f"{did}.txt"
        if not fp.is_file():
            continue
        try:
            raw = fp.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        before = [
            (e.get("date") or "").strip() if e.get("date") is not None else "" for e in evs
        ]
        enrich_events_from_source_text(evs, raw)
        for e, b in zip(evs, before, strict=True):
            after = (e.get("date") or "").strip() if e.get("date") is not None else ""
            if not b and after:
                changed += 1
    if changed:
        existing.sort(key=_sort_key)
        events_path.parent.mkdir(parents=True, exist_ok=True)
        events_path.write_text(json.dumps(existing, indent=2), encoding="utf-8")
    return changed
