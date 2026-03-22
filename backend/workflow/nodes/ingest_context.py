from __future__ import annotations

from schemas import StoreDocumentRequest
from workflow.state import CaseState


def ingest_context_node(state: CaseState) -> dict:
    """Wrap store_document_for_rag to persist, parse, chunk, embed, and store the document."""
    from rag.router import store_document_for_rag

    payload = StoreDocumentRequest(
        case_id=state["case_id"],
        raw_text=state["raw_text"],
        source=state["source"],
        defer_case_index=True,
    )
    result = store_document_for_rag(payload)

    doc_record = {
        "doc_id": result.doc_id,
        "case_id": state["case_id"],
        "source": state["source"],
        "summary": result.summary,
        "num_chunks": result.num_chunks,
    }
    return {"documents": state["documents"] + [doc_record]}
