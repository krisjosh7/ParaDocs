from __future__ import annotations

import logging
from datetime import datetime, timezone

from fastapi import APIRouter

from schemas import (
    ChunkMetadataOut,
    ChunkResult,
    Document,
    IngestRequest,
    IngestResponse,
    QueryInput,
    QueryResult,
    StoreDocumentRequest,
    StoreResponse,
    StructuredDocument,
    StructuredHitOut,
)
from storage import generate_doc_id, utc_now_iso, write_metadata, write_raw_text, write_structured
from case_events_merge import append_events_from_ingest

from .chunking import chunk_text
from .parser import parse_legal_structure
from .vector_store import delete_chunks_for_doc_id, query_case, upsert_text_records

_logger = logging.getLogger(__name__)

router = APIRouter(tags=["rag"])


def _timestamp_iso(ts: str | datetime | None) -> str:
    if ts is None:
        return utc_now_iso()
    if isinstance(ts, datetime):
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)
        return ts.isoformat()
    return ts


def _build_document_for_store(payload: StoreDocumentRequest) -> Document:
    doc_id = generate_doc_id()
    ts = _timestamp_iso(payload.timestamp)
    url = (payload.source_url or "").strip() or None
    return Document(
        case_id=payload.case_id,
        doc_id=doc_id,
        raw_text=payload.raw_text,
        source=payload.source,
        timestamp=ts,
        source_url=url,
    )


def _event_chunk_text(event) -> str:
    parts = [event.event.strip()]
    if event.source_span and event.source_span.strip():
        parts.append(event.source_span.strip())
    return "\n".join(p for p in parts if p)


def _claim_chunk_text(claim) -> str:
    parts = [claim.type.strip()]
    if claim.source_span and claim.source_span.strip():
        parts.append(claim.source_span.strip())
    return "\n".join(p for p in parts if p)


def _dedupe_events(structured: StructuredDocument):
    seen: set[tuple[str, str]] = set()
    out = []
    for ev in structured.events:
        if not ev.event.strip():
            continue
        key = (ev.event.strip().lower(), (ev.source_span or "").strip())
        if key in seen:
            continue
        seen.add(key)
        out.append(ev)
    return out


def _dedupe_claims(structured: StructuredDocument):
    seen: set[tuple[str, str]] = set()
    out = []
    for cl in structured.claims:
        if not cl.type.strip():
            continue
        key = (cl.type.strip().lower(), (cl.source_span or "").strip())
        if key in seen:
            continue
        seen.add(key)
        out.append(cl)
    return out


def _structured_vector_records(document: Document, structured: StructuredDocument) -> list[dict]:
    """Summary, event, and claim chunks per spec (atomic, explicit types)."""
    case_id = document.case_id
    doc_id = document.doc_id
    source = document.source
    timestamp = document.timestamp
    records: list[dict] = []

    if structured.summary.text.strip():
        records.append(
            {
                "id": f"{doc_id}-summary",
                "document": structured.summary.text.strip(),
                "metadata": {
                    "case_id": case_id,
                    "doc_id": doc_id,
                    "source": source,
                    "timestamp": timestamp,
                    "chunk_index": -1,
                    "type": "summary",
                    "confidence": float(structured.summary.confidence),
                    "related_event": "",
                    "related_claim": "",
                },
            }
        )

    for idx, event in enumerate(_dedupe_events(structured)):
        records.append(
            {
                "id": f"{doc_id}-event-{idx}",
                "document": _event_chunk_text(event),
                "metadata": {
                    "case_id": case_id,
                    "doc_id": doc_id,
                    "source": source,
                    "timestamp": timestamp,
                    "chunk_index": idx,
                    "type": "event",
                    "confidence": float(event.confidence),
                    "related_event": event.event.strip(),
                    "related_claim": "",
                },
            }
        )

    for idx, claim in enumerate(_dedupe_claims(structured)):
        records.append(
            {
                "id": f"{doc_id}-claim-{idx}",
                "document": _claim_chunk_text(claim),
                "metadata": {
                    "case_id": case_id,
                    "doc_id": doc_id,
                    "source": source,
                    "timestamp": timestamp,
                    "chunk_index": idx,
                    "type": "claim",
                    "confidence": float(claim.confidence),
                    "related_event": "",
                    "related_claim": claim.type.strip(),
                },
            }
        )

    return records


def _raw_vector_records(document: Document, raw_chunks: list[str]) -> list[dict]:
    records: list[dict] = []
    for idx, chunk in enumerate(raw_chunks):
        records.append(
            {
                "id": f"{document.doc_id}-raw-{idx}",
                "document": chunk,
                "metadata": {
                    "case_id": document.case_id,
                    "doc_id": document.doc_id,
                    "source": document.source,
                    "timestamp": document.timestamp,
                    "chunk_index": idx,
                    "type": "raw",
                    "related_event": "",
                    "related_claim": "",
                },
            }
        )
    return records


@router.post("/parse", response_model=StructuredDocument)
def parse_endpoint(document: Document) -> StructuredDocument:
    return parse_legal_structure(document)


@router.post("/ingest", response_model=IngestResponse)
def ingest_endpoint(payload: IngestRequest) -> IngestResponse:
    document = payload.document
    structured = payload.structured
    delete_chunks_for_doc_id(document.doc_id)
    raw_chunks = chunk_text(document.raw_text)
    raw_records = _raw_vector_records(document, raw_chunks)
    structured_records = _structured_vector_records(document, structured)

    upsert_text_records(raw_records)
    upsert_text_records(structured_records)

    total_chunks = len(raw_records) + len(structured_records)

    write_structured(document.case_id, document.doc_id, structured)
    meta_row: dict = {
        "case_id": document.case_id,
        "doc_id": document.doc_id,
        "source": document.source,
        "timestamp": document.timestamp,
        "num_raw_chunks": len(raw_records),
        "num_structured_chunks": len(structured_records),
        "num_chunks": total_chunks,
        "status": "ingested",
    }
    if document.source_url:
        meta_row["source_url"] = document.source_url
    write_metadata(document.case_id, document.doc_id, meta_row)

    # Phase 1 case event index: merge this doc's events into cases/{case_id}/events.json
    # (runs for every ingest: Discovery /store pipeline, POST /ingest, POST /store, etc.)
    try:
        append_events_from_ingest(document.case_id, document.doc_id, structured)
    except Exception:
        _logger.exception(
            "Failed to merge events into events.json for case_id=%s doc_id=%s",
            document.case_id,
            document.doc_id,
        )

    return IngestResponse(num_chunks=total_chunks, doc_id=document.doc_id)


def store_document_for_rag(payload: StoreDocumentRequest) -> StoreResponse:
    """Parse, persist, and embed a document into Chroma (same behavior as POST /store)."""
    document = _build_document_for_store(payload)
    write_raw_text(document.case_id, document.doc_id, document.raw_text)
    structured = parse_legal_structure(document)
    ingest_result = ingest_endpoint(IngestRequest(document=document, structured=structured))
    return StoreResponse(
        doc_id=document.doc_id,
        status="stored",
        num_chunks=ingest_result.num_chunks,
        summary=structured.summary.text,
    )


@router.post("/store", response_model=StoreResponse)
def store_endpoint(payload: StoreDocumentRequest) -> StoreResponse:
    return store_document_for_rag(payload)


@router.post("/query", response_model=QueryResult)
def query_endpoint(payload: QueryInput) -> QueryResult:
    type_filter = payload.filters.type
    hits = query_case(
        payload.case_id,
        payload.query,
        top_k=payload.top_k,
        type_filter=type_filter,
    )

    chunks: list[ChunkResult] = []
    structured_hits: list[StructuredHitOut] = []
    source_set: set[str] = set()

    for hit in hits:
        md = hit.get("metadata") or {}
        doc_id = str(md.get("doc_id", ""))
        chunk_id = str(hit.get("id", ""))
        h_type = str(md.get("type", "raw"))
        source = str(md.get("source", ""))
        ts = str(md.get("timestamp", ""))
        text = str(hit.get("document", ""))
        score = float(hit.get("score", 0.0))

        source_set.add(doc_id)
        chunks.append(
            ChunkResult(
                chunk_id=chunk_id,
                doc_id=doc_id,
                text=text,
                score=score,
                metadata=ChunkMetadataOut(source=source, timestamp=ts, type=h_type),
            )
        )
        if h_type in ("summary", "event", "claim"):
            structured_hits.append(
                StructuredHitOut(
                    type=h_type,  # type: ignore[arg-type]
                    value=text,
                    confidence=float(md.get("confidence", 0.0)),
                    doc_id=doc_id,
                )
            )

    return QueryResult(
        query=payload.query,
        chunks=chunks,
        structured_hits=structured_hits,
        sources=sorted(source_set),
    )
