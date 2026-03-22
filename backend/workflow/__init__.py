from workflow.state import CaseState
from workflow.graph import case_workflow


def run_case_workflow(state: CaseState) -> CaseState:
    """Execute the Phase 1 case-initialization graph and return the updated state."""
    return case_workflow.invoke(state)
