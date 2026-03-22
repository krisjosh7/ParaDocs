from __future__ import annotations

from typing import Any, TypedDict


class TimelineState(TypedDict):
    """LangGraph state for Phase 2 timeline rebuild (load → build → persist)."""

    case_id: str
    events: list[dict[str, Any]]
    timelines_payload: dict[str, Any]


def initial_timeline_state(case_id: str) -> TimelineState:
    return {
        "case_id": case_id,
        "events": [],
        "timelines_payload": {},
    }
