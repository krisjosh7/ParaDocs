from __future__ import annotations

import json

from schemas import StructuredDocument
from storage import default_cases_root
from workflow.state import CaseState


def extract_events_node(state: CaseState) -> dict:
    """Read the structured JSON written by ingest_context and collect events."""
    last_doc = state["documents"][-1]
    doc_id = last_doc["doc_id"]
    case_id = state["case_id"]

    structured_path = default_cases_root() / case_id / "structured" / f"{doc_id}.json"
    raw = json.loads(structured_path.read_text(encoding="utf-8"))
    structured = StructuredDocument.model_validate(raw)

    event_dicts = []
    for ev in structured.events:
        d = ev.model_dump()
        d["doc_id"] = doc_id
        event_dicts.append(d)

    return {
        "structured": state["structured"] + [structured.model_dump()],
        "events": state["events"] + event_dicts,
    }
