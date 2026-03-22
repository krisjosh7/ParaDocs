from __future__ import annotations

import logging

from case_events_merge import backfill_case_event_dates
from timeline_logic import rebuild_case_timeline
from workflow.state import CaseState

_logger = logging.getLogger(__name__)


def run_reasoning_phase_node(state: CaseState) -> dict:
    """
    Post–timeline/research enrichment: backfill event dates from source text and
    refresh timelines when the event index changes.
    """
    case_id = state["case_id"]
    _logger.info("Reasoning phase: backfill + timeline sync start case_id=%s", case_id)
    changed = backfill_case_event_dates(case_id)
    timeline_refreshed = False
    if changed > 0:
        rebuild_case_timeline(case_id)
        timeline_refreshed = True
    _logger.info(
        "Reasoning phase: done case_id=%s events_date_backfills=%d timeline_refreshed=%s",
        case_id,
        changed,
        timeline_refreshed,
    )
    return {
        "reasoning_backfill_changes": changed,
        "reasoning_timeline_refreshed": timeline_refreshed,
    }
