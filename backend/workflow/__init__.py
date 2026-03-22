from workflow.graph import case_workflow
from workflow.state import CaseState
from workflow.timeline_graph import run_timeline_workflow
from workflow.timeline_state import TimelineState, initial_timeline_state


def run_case_workflow(state: CaseState) -> CaseState:
    """Execute the Phase 1 case-initialization graph and return the updated state."""
    return case_workflow.invoke(state)


__all__ = [
    "CaseState",
    "TimelineState",
    "case_workflow",
    "initial_timeline_state",
    "run_case_workflow",
    "run_timeline_workflow",
]
