"""
LangGraph case pipeline: ingest → events → timeline → research.

Topology:
    START
      -> ingest_context   (persist + parse + chunk + embed; defers events/timeline in RAG)
      -> extract_events   (read structured JSON from disk, collect events)
      -> normalize_events (merge + dedupe + persist to events.json)
      -> rebuild_timeline (Phase 2: timelines.json)
      -> run_research     (Phase 3: async research subgraph)
      -> END
"""

from langgraph.graph import StateGraph, START, END

from workflow.state import CaseState
from workflow.nodes.ingest_context import ingest_context_node
from workflow.nodes.extract_events import extract_events_node
from workflow.nodes.normalize_events import normalize_events_node
from workflow.nodes.rebuild_timeline import rebuild_timeline_node
from workflow.nodes.run_research_phase import run_research_phase_node


def build_case_workflow() -> StateGraph:
    builder = StateGraph(CaseState)

    builder.add_node("ingest_context", ingest_context_node)
    builder.add_node("extract_events", extract_events_node)
    builder.add_node("normalize_events", normalize_events_node)
    builder.add_node("rebuild_timeline", rebuild_timeline_node)
    builder.add_node("run_research", run_research_phase_node)

    builder.add_edge(START, "ingest_context")
    builder.add_edge("ingest_context", "extract_events")
    builder.add_edge("extract_events", "normalize_events")
    builder.add_edge("normalize_events", "rebuild_timeline")
    builder.add_edge("rebuild_timeline", "run_research")
    builder.add_edge("run_research", END)

    return builder


case_workflow = build_case_workflow().compile()
