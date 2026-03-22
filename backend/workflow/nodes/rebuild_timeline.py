from __future__ import annotations

import logging

from timeline_logic import rebuild_case_timeline
from workflow.state import CaseState

_logger = logging.getLogger(__name__)


def rebuild_timeline_node(state: CaseState) -> dict:
    """Run Phase 2 timeline workflow and attach timelines payload to case state."""
    case_id = state["case_id"]
    _logger.info("Phase 2/3 timeline: rebuild start case_id=%s", case_id)
    payload = rebuild_case_timeline(case_id)
    primary = (payload.get("primary") or {}).get("entries") if isinstance(payload.get("primary"), dict) else []
    n_primary = len(primary) if isinstance(primary, list) else 0
    conflicts = payload.get("conflicts") or []
    branches = payload.get("branches") or []
    _logger.info(
        "Phase 2/3 timeline: rebuild done case_id=%s primary_entries=%d conflicts=%d branches=%d",
        case_id,
        n_primary,
        len(conflicts) if isinstance(conflicts, list) else 0,
        len(branches) if isinstance(branches, list) else 0,
    )
    return {"timelines": payload}
