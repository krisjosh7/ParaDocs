from __future__ import annotations

import json
import os
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
