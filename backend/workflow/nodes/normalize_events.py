from __future__ import annotations

import logging

from case_events_merge import merge_new_events_into_case_file
from workflow.state import CaseState

_logger = logging.getLogger(__name__)


def normalize_events_node(state: CaseState) -> dict:
    """Deduplicate, sort, and persist the accumulated events to events.json."""
    case_id = state["case_id"]
    _logger.info(
        "Phase 1/3 events: normalize_events start case_id=%s pending_events=%d",
        case_id,
        len(state["events"]),
    )
    normalized = merge_new_events_into_case_file(case_id, state["events"])
    _logger.info(
        "Phase 1/3 events: normalize_events done case_id=%s total_events=%d",
        case_id,
        len(normalized),
    )
    return {"events": normalized}
