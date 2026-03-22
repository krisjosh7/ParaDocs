from __future__ import annotations

from timeline_logic import build_timeline_payload, read_case_events, write_timelines_json
from workflow.timeline_state import TimelineState


def load_events_node(state: TimelineState) -> dict:
    events = read_case_events(state["case_id"])
    return {"events": events}


def build_timeline_node(state: TimelineState) -> dict:
    payload = build_timeline_payload(state["case_id"], state["events"])
    return {"timelines_payload": payload}


def persist_timeline_node(state: TimelineState) -> dict:
    write_timelines_json(state["case_id"], state["timelines_payload"])
    return {}
