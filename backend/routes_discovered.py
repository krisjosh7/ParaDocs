from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from context_catalog import validate_case_id
from rag.vector_store import delete_chunks_for_doc_id
from storage import delete_stored_document_files, list_discovered_case_documents

router = APIRouter(prefix="/cases/{case_id}", tags=["cases"])


class DiscoveredDocumentOut(BaseModel):
    doc_id: str
    metadata: dict[str, Any]
    structured: dict[str, Any] | None = None
    sourceUrl: str | None = None


class DiscoveredDocumentListOut(BaseModel):
    items: list[DiscoveredDocumentOut]


@router.get("/discovered-documents", response_model=DiscoveredDocumentListOut)
def list_discovered_documents(case_id: str) -> DiscoveredDocumentListOut:
    """List on-disk metadata (+ structured parse) for documents ingested into the case (e.g. live session saves)."""
    try:
        validate_case_id(case_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    rows = list_discovered_case_documents(case_id)
    return DiscoveredDocumentListOut(
        items=[
            DiscoveredDocumentOut(
                doc_id=r["doc_id"],
                metadata=r["metadata"],
                structured=r.get("structured"),
                sourceUrl=r.get("source_url"),
            )
            for r in rows
        ],
    )


@router.delete("/discovered-documents/{doc_id}")
def delete_discovered_document(case_id: str, doc_id: str) -> dict[str, str]:
    """Remove a RAG-ingested case document (metadata, structured, raw text, and Chroma chunks)."""
    try:
        validate_case_id(case_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    did = (doc_id or "").strip()
    if not did or ".." in did or "/" in did or "\\" in did:
        raise HTTPException(status_code=400, detail="Invalid doc_id")

    # Idempotent: catalog delete may remove metadata first (same rag_doc_id as library ingest).
    # Always best-effort clear vectors + documents/structured/metadata for this doc_id.
    delete_chunks_for_doc_id(did)
    delete_stored_document_files(case_id, did)
    return {"status": "deleted", "id": did}
