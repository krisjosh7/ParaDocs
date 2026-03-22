from __future__ import annotations

import json
import logging

from schemas import StructuredDocument
from storage import default_cases_root
from workflow.state import CaseState

_logger = logging.getLogger(__name__)


def extract_events_node(state: CaseState) -> dict:
    """Read the structured JSON written by ingest_context and collect events."""
    last_doc = state["documents"][-1]
    doc_id = last_doc["doc_id"]
    case_id = state["case_id"]

    structured_path = default_cases_root() / case_id / "structured" / f"{doc_id}.json"
    raw = json.loads(structured_path.read_text(encoding="utf-8"))
    structured = StructuredDocument.model_validate(raw)

    ctx_id = state.get("context_id")
    event_dicts = []
    for ev in structured.events:
        d = ev.model_dump()
        d["doc_id"] = doc_id
        if ctx_id:
            d["context_id"] = ctx_id
        event_dicts.append(d)

    _logger.info(
        "Phase 1/3 events: extract_events done case_id=%s doc_id=%s new_events=%d",
        case_id,
        doc_id,
        len(event_dicts),
    )
    return {
        "structured": state["structured"] + [structured.model_dump()],
        "events": state["events"] + event_dicts,
    }
