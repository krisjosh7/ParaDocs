from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path
from uuid import uuid4

from storage import default_cases_root

_CASE_ID_RE = re.compile(r"^[\w.-]{1,256}$")


def validate_case_id(case_id: str) -> str:
    cid = (case_id or "").strip()
    if not cid or not _CASE_ID_RE.match(cid):
        raise ValueError("Invalid case_id")
    if ".." in cid:
        raise ValueError("Invalid case_id")
    return cid


def context_library_paths(case_id: str) -> dict[str, Path]:
    cid = validate_case_id(case_id)
    base = default_cases_root() / cid / "contexts"
    files = base / "files"
    catalog_path = base / "catalog.json"
    base.mkdir(parents=True, exist_ok=True)
    files.mkdir(parents=True, exist_ok=True)
    return {"base": base, "files": files, "catalog": catalog_path}


def read_catalog(case_id: str) -> list[dict]:
    paths = context_library_paths(case_id)
    p = paths["catalog"]
    if not p.is_file():
        return []
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return []
    if not isinstance(data, list):
        return []
    return [x for x in data if isinstance(x, dict)]


def write_catalog(case_id: str, items: list[dict]) -> None:
    paths = context_library_paths(case_id)
    paths["catalog"].write_text(json.dumps(items, indent=2), encoding="utf-8")


def set_rag_doc_id_for_context(case_id: str, context_id: str, rag_doc_id: str) -> None:
    """Persist the RAG store doc_id on a context row after background ingest (for cascade delete)."""
    cid = (context_id or "").strip()
    rid = (rag_doc_id or "").strip()
    if not cid or not rid:
        return
    items = read_catalog(case_id)
    changed = False
    for row in items:
        if str(row.get("id")) == cid:
            row["rag_doc_id"] = rid
            changed = True
            break
    if changed:
        write_catalog(case_id, items)


def format_added_label(iso_ts: str) -> str:
    try:
        raw = iso_ts.replace("Z", "+00:00")
        dt = datetime.fromisoformat(raw)
        local = dt.astimezone() if dt.tzinfo else dt
        return local.strftime("%b %d, %Y · %H:%M")
    except (ValueError, TypeError):
        return iso_ts


def make_text_preview(text: str, max_len: int = 200) -> str:
    line = " ".join(text.replace("\r\n", "\n").strip().split())
    if len(line) <= max_len:
        return line
    return line[: max_len - 1].rstrip() + "…"


def new_context_id() -> str:
    return f"ctx-{uuid4()}"


def filter_items_by_query(items: list[dict], q: str | None) -> list[dict]:
    if not q or not q.strip():
        return items
    needle = q.strip().lower()
    out: list[dict] = []
    for it in items:
        title = str(it.get("title", "")).lower()
        caption = str(it.get("caption", "")).lower()
        fname = str(it.get("file_name", "") or "").lower()
        body = str(it.get("text_full", "") or "").lower()
        src_url = str(it.get("source_url", "") or "").lower()
        if needle in title or needle in caption or needle in fname or needle in body or needle in src_url:
            out.append(it)
    return out
