from __future__ import annotations

import logging

from research.graph import research_subgraph
from research.state import initial_research_graph_state
from workflow.state import CaseState

_logger = logging.getLogger(__name__)


async def run_research_phase_node(state: CaseState) -> dict:
    """Run the async research subgraph (Phase 3) and copy outputs into CaseState."""
    case_id = state["case_id"]
    _logger.info("Phase 3/3 research: subgraph start case_id=%s", case_id)
    initial = initial_research_graph_state(case_id)
    final = await research_subgraph.ainvoke(initial)
    try:
        from research.case_summary import record_research_run

        record_research_run(
            case_id,
            list(final.get("all_stored_results") or []),
            final.get("stop_reason"),
            int(final.get("iteration") or 0),
        )
    except Exception:
        _logger.exception("Failed to persist research summary for case %s", case_id)
    stored = final.get("all_stored_results") or []
    _logger.info(
        "Phase 3/3 research: subgraph done case_id=%s iterations=%s stop_reason=%s stored_results=%d",
        case_id,
        final.get("iteration"),
        final.get("stop_reason"),
        len(stored) if isinstance(stored, list) else 0,
    )
    return {
        "research_results": final["all_stored_results"],
        "research_stop_reason": final.get("stop_reason"),
        "research_iteration": int(final.get("iteration") or 0),
    }
