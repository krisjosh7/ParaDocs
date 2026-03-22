from __future__ import annotations

import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from schemas import StructuredDocument


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def default_cases_root() -> Path:
    configured = os.environ.get("CASES_ROOT", "").strip()
    if configured:
        return Path(configured).expanduser().resolve()
    return Path(__file__).resolve().parent / "cases"


def ensure_case_dirs(case_id: str) -> dict[str, Path]:
    base = default_cases_root() / case_id
    paths = {
        "base": base,
        "documents": base / "documents",
        "structured": base / "structured",
        "metadata": base / "metadata",
        "embeddings": base / "embeddings",
        "logs": base / "logs",
    }
    for path in paths.values():
        path.mkdir(parents=True, exist_ok=True)
    return paths


def generate_doc_id() -> str:
    return str(uuid4())


def write_raw_text(case_id: str, doc_id: str, raw_text: str) -> Path:
    paths = ensure_case_dirs(case_id)
    out = paths["documents"] / f"{doc_id}.txt"
    out.write_text(raw_text, encoding="utf-8")
    return out


def write_structured(case_id: str, doc_id: str, structured: StructuredDocument) -> Path:
    paths = ensure_case_dirs(case_id)
    out = paths["structured"] / f"{doc_id}.json"
    out.write_text(structured.model_dump_json(indent=2), encoding="utf-8")
    return out


def write_metadata(case_id: str, doc_id: str, metadata: dict) -> Path:
    paths = ensure_case_dirs(case_id)
    out = paths["metadata"] / f"{doc_id}.json"
    out.write_text(json.dumps(metadata, indent=2), encoding="utf-8")
    return out


_SOURCE_LINE_RE = re.compile(r"(?im)^Source:\s*(https?://\S+)")


def extract_source_url_from_raw_document(case_id: str, doc_id: str) -> str | None:
    """Parse `Source: https://...` from live session /store raw text (documents/{doc_id}.txt)."""
    doc_id = (doc_id or "").strip()
    if not doc_id or ".." in doc_id or "/" in doc_id or "\\" in doc_id:
        return None
    fp = default_cases_root() / case_id / "documents" / f"{doc_id}.txt"
    if not fp.is_file():
        return None
    try:
        text = fp.read_text(encoding="utf-8", errors="replace")[:65536]
    except OSError:
        return None
    m = _SOURCE_LINE_RE.search(text)
    if not m:
        return None
    url = m.group(1).strip()
    while url and url[-1] in ".,;)]}\"'":
        url = url[:-1]
    return url or None


def list_discovered_case_documents(case_id: str) -> list[dict]:
    """
    Each RAG-ingested document under a case has metadata/{doc_id}.json and optionally
    structured/{doc_id}.json (e.g. after live session "Save to context" or POST /store).
    """
    base = default_cases_root() / case_id
    meta_dir = base / "metadata"
    struct_dir = base / "structured"
    if not meta_dir.is_dir():
        return []
    out: list[dict] = []
    for fp in meta_dir.glob("*.json"):
        doc_id = fp.stem
        if not doc_id or ".." in doc_id or "/" in doc_id or "\\" in doc_id:
            continue
        try:
            meta = json.loads(fp.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue
        if not isinstance(meta, dict):
            continue
        structured = None
        sp = struct_dir / f"{doc_id}.json"
        if sp.is_file():
            try:
                structured = json.loads(sp.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                structured = None
        if structured is not None and not isinstance(structured, dict):
            structured = None
        meta_url = meta.get("source_url")
        source_url = (
            str(meta_url).strip()
            if isinstance(meta_url, str) and str(meta_url).strip()
            else None
        ) or extract_source_url_from_raw_document(case_id, doc_id)
        out.append(
            {
                "doc_id": doc_id,
                "metadata": meta,
                "structured": structured,
                "source_url": source_url,
            }
        )

    def _ts(row: dict) -> str:
        m = row.get("metadata") or {}
        return str(m.get("timestamp") or "")

    out.sort(key=_ts, reverse=True)
    return out


def delete_stored_document_files(case_id: str, doc_id: str) -> None:
    """Remove documents/structured/metadata files for a RAG doc_id (best-effort)."""
    doc_id = (doc_id or "").strip()
    if not doc_id or ".." in doc_id or "/" in doc_id or "\\" in doc_id:
        return
    base = default_cases_root() / case_id
    for sub, ext in (
        ("documents", ".txt"),
        ("structured", ".json"),
        ("metadata", ".json"),
    ):
        fp = base / sub / f"{doc_id}{ext}"
        try:
            fp.unlink(missing_ok=True)
        except OSError:
            pass
