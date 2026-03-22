from __future__ import annotations

import logging

from schemas import StoreDocumentRequest
from workflow.state import CaseState

_logger = logging.getLogger(__name__)


def ingest_context_node(state: CaseState) -> dict:
    """Wrap store_document_for_rag to persist, parse, chunk, embed, and store the document."""
    from rag.router import store_document_for_rag

    case_id = state["case_id"]
    ctx = state.get("context_id")
    _logger.info(
        "Phase 1/3 events: ingest_context start case_id=%s source=%s context_id=%s",
        case_id,
        state.get("source"),
        ctx,
    )

    payload = StoreDocumentRequest(
        case_id=state["case_id"],
        raw_text=state["raw_text"],
        source=state["source"],
        defer_case_index=True,
    )
    result = store_document_for_rag(payload)

    doc_record = {
        "doc_id": result.doc_id,
        "case_id": case_id,
        "source": state["source"],
        "summary": result.summary,
        "num_chunks": result.num_chunks,
    }
    _logger.info(
        "Phase 1/3 events: ingest_context done case_id=%s doc_id=%s num_chunks=%s",
        case_id,
        result.doc_id,
        result.num_chunks,
    )
    return {"documents": state["documents"] + [doc_record]}
