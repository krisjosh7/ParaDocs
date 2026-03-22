"""
LangGraph case pipeline: ingest → events → timeline → [research?] → reasoning.

Topology:
    START
      -> ingest_context   (persist + parse + chunk + embed; defers events/timeline in RAG)
      -> extract_events   (read structured JSON from disk, collect events)
      -> normalize_events (merge + dedupe + persist to events.json)
      -> rebuild_timeline (Phase 2: timelines.json; always)
      -> run_research     (Phase 3: async research subgraph, once per case if context is sufficient)
      -> run_reasoning    (Phase 4: event date backfill + timeline refresh if needed)
      -> END
"""

from langgraph.graph import StateGraph, START, END

from workflow.state import CaseState
from workflow.pipeline_state import read_pipeline_state
from workflow.research_gate import should_run_initial_research
from workflow.nodes.ingest_context import ingest_context_node
from workflow.nodes.extract_events import extract_events_node
from workflow.nodes.normalize_events import normalize_events_node
from workflow.nodes.rebuild_timeline import rebuild_timeline_node
from workflow.nodes.run_research_phase import run_research_phase_node
from workflow.nodes.run_reasoning_phase import run_reasoning_phase_node


def _route_after_timeline(state: CaseState) -> str:
    if should_run_initial_research(state["case_id"], state):
        return "run_research"
    return "skip_research"


def build_case_workflow() -> StateGraph:
    builder = StateGraph(CaseState)

    builder.add_node("ingest_context", ingest_context_node)
    builder.add_node("extract_events", extract_events_node)
    builder.add_node("normalize_events", normalize_events_node)
    builder.add_node("rebuild_timeline", rebuild_timeline_node)
    builder.add_node("run_research", run_research_phase_node)
    builder.add_node("skip_research", _skip_research_node)
    builder.add_node("run_reasoning", run_reasoning_phase_node)

    builder.add_edge(START, "ingest_context")
    builder.add_edge("ingest_context", "extract_events")
    builder.add_edge("extract_events", "normalize_events")
    builder.add_edge("normalize_events", "rebuild_timeline")
    builder.add_conditional_edges(
        "rebuild_timeline",
        _route_after_timeline,
        {"run_research": "run_research", "skip_research": "skip_research"},
    )
    builder.add_edge("run_research", "run_reasoning")
    builder.add_edge("skip_research", "run_reasoning")
    builder.add_edge("run_reasoning", END)

    return builder


def _skip_research_node(state: CaseState) -> dict:
    """Bridge when automatic research is not run; mirrors run_research skip metadata for API clarity."""
    case_id = state["case_id"]
    if read_pipeline_state(case_id).get("initial_research_completed"):
        return {
            "research_results": [],
            "research_stop_reason": "skipped_already_completed",
            "research_iteration": 0,
        }
    return {
        "research_results": [],
        "research_stop_reason": "skipped_insufficient_context",
        "research_iteration": 0,
    }


case_workflow = build_case_workflow().compile()
