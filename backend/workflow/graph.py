"""
LangGraph subgraph for the case initialization workflow (Phase 1).

Topology:
    START
      -> ingest_context   (persist + parse + chunk + embed via existing RAG pipeline)
      -> extract_events   (read structured JSON from disk, collect events)
      -> normalize_events (dedupe + sort + persist to events.json)
      -> END
"""

from langgraph.graph import StateGraph, START, END

from workflow.state import CaseState
from workflow.nodes.ingest_context import ingest_context_node
from workflow.nodes.extract_events import extract_events_node
from workflow.nodes.normalize_events import normalize_events_node


def build_case_workflow() -> StateGraph:
    builder = StateGraph(CaseState)

    builder.add_node("ingest_context", ingest_context_node)
    builder.add_node("extract_events", extract_events_node)
    builder.add_node("normalize_events", normalize_events_node)

    builder.add_edge(START, "ingest_context")
    builder.add_edge("ingest_context", "extract_events")
    builder.add_edge("extract_events", "normalize_events")
    builder.add_edge("normalize_events", END)

    return builder


case_workflow = build_case_workflow().compile()
