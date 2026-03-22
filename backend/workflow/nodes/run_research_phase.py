from __future__ import annotations

from research.graph import research_subgraph
from research.state import initial_research_graph_state
from workflow.state import CaseState


async def run_research_phase_node(state: CaseState) -> dict:
    """Run the async research subgraph (Phase 3) and copy outputs into CaseState."""
    initial = initial_research_graph_state(state["case_id"])
    final = await research_subgraph.ainvoke(initial)
    return {
        "research_results": final["all_stored_results"],
        "research_stop_reason": final.get("stop_reason"),
        "research_iteration": int(final.get("iteration") or 0),
    }
