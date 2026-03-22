"""
LangGraph subgraph: rebuild timelines.json from events.json.

Topology:
    START -> load_events -> build_timeline -> persist_timeline -> END
"""

from __future__ import annotations

from langgraph.graph import END, START, StateGraph

from workflow.nodes.timeline_nodes import build_timeline_node, load_events_node, persist_timeline_node
from workflow.timeline_state import TimelineState, initial_timeline_state


def build_timeline_workflow() -> StateGraph:
    builder = StateGraph(TimelineState)
    builder.add_node("load_events", load_events_node)
    builder.add_node("build_timeline", build_timeline_node)
    builder.add_node("persist_timeline", persist_timeline_node)

    builder.add_edge(START, "load_events")
    builder.add_edge("load_events", "build_timeline")
    builder.add_edge("build_timeline", "persist_timeline")
    builder.add_edge("persist_timeline", END)
    return builder


timeline_workflow = build_timeline_workflow().compile()


def run_timeline_workflow(case_id: str) -> TimelineState:
    """Execute the timeline graph and return the final state (includes timelines_payload)."""
    return timeline_workflow.invoke(initial_timeline_state(case_id))
