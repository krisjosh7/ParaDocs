"""
Wipe a case's Discovery context library, timeline index, and RAG-backed documents.

Use when you want an empty case without deleting the case folder itself.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from context_catalog import context_library_paths, read_catalog, validate_case_id, write_catalog
from storage import default_cases_root, delete_stored_document_files
from timeline_logic import empty_timeline_payload, write_timelines_json


def _safe_stem(name: str) -> bool:
    s = (name or "").strip()
    return bool(s) and ".." not in s and "/" not in s and "\\" not in s


def _collect_rag_doc_ids(case_id: str) -> set[str]:
    """All doc_ids that may have Chroma rows or files under documents/structured/metadata."""
    base = default_cases_root() / case_id
    ids: set[str] = set()
    for row in read_catalog(case_id):
        rid = str(row.get("rag_doc_id") or "").strip()
        if _safe_stem(rid):
            ids.add(rid)
    for sub, suffixes in (
        ("metadata", (".json",)),
        ("structured", (".json",)),
        ("documents", (".txt",)),
    ):
        d = base / sub
        if not d.is_dir():
            continue
        for fp in d.iterdir():
            if fp.is_file() and fp.suffix in suffixes and _safe_stem(fp.stem):
                ids.add(fp.stem)
    return ids


def reset_case_context_timeline_and_rag(
    case_id: str,
    *,
    delete_chunks_for_doc_id: Callable[[str], None] | None = None,
) -> dict[str, int]:
    """
    Clear context catalog + files, events.json, timelines.json, and remove each RAG doc
    from Chroma and from documents/structured/metadata. Keeps contexts/sample-*.txt helpers.
    """
    cid = validate_case_id(case_id)
    doc_ids = _collect_rag_doc_ids(cid)

    _delete_chunks = delete_chunks_for_doc_id
    if _delete_chunks is None:
        from rag.chroma_collection import delete_chunks_for_doc_id as _delete_chunks

    for did in doc_ids:
        _delete_chunks(did)
        delete_stored_document_files(cid, did)

    paths = context_library_paths(cid)
    files_dir = paths["files"]
    if files_dir.is_dir():
        for fp in files_dir.iterdir():
            if fp.is_file():
                try:
                    fp.unlink()
                except OSError:
                    pass
    write_catalog(cid, [])

    base = default_cases_root() / cid
    events_path = base / "events.json"
    events_path.parent.mkdir(parents=True, exist_ok=True)
    events_path.write_text("[]", encoding="utf-8")

    write_timelines_json(cid, empty_timeline_payload(cid))

    emb = base / "embeddings"
    if emb.is_dir():
        for fp in emb.glob("*"):
            if fp.is_file():
                try:
                    fp.unlink()
                except OSError:
                    pass

    return {
        "rag_doc_ids_cleared": len(doc_ids),
    }
