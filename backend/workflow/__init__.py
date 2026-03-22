from workflow.graph import case_workflow
from workflow.state import CaseState, initial_case_state
from workflow.timeline_graph import run_timeline_workflow
from workflow.timeline_state import TimelineState, initial_timeline_state


async def run_case_workflow(state: CaseState) -> CaseState:
    """Run the full case pipeline (Phases 1–3). Must be awaited (research nodes are async)."""
    return await case_workflow.ainvoke(state)


__all__ = [
    "CaseState",
    "TimelineState",
    "case_workflow",
    "initial_case_state",
    "initial_timeline_state",
    "run_case_workflow",
    "run_timeline_workflow",
]
