from __future__ import annotations

from case_events_merge import merge_new_events_into_case_file
from workflow.state import CaseState


def normalize_events_node(state: CaseState) -> dict:
    """Deduplicate, sort, and persist the accumulated events to events.json."""
    case_id = state["case_id"]
    normalized = merge_new_events_into_case_file(case_id, state["events"])
    return {"events": normalized}
