from __future__ import annotations

from timeline_logic import rebuild_case_timeline
from workflow.state import CaseState


def rebuild_timeline_node(state: CaseState) -> dict:
    """Run Phase 2 timeline workflow and attach timelines payload to case state."""
    payload = rebuild_case_timeline(state["case_id"])
    return {"timelines": payload}
