"""Whether the case workflow should run the automatic research subgraph."""

from __future__ import annotations

from typing import Any

from workflow.pipeline_state import read_pipeline_state
from workflow.state import CaseState

# When the parser leaves confidence at 0, still give a small weight so presence counts.
CONFIDENCE_FLOOR = 0.5
# Sum of effective confidences (events + structured extras) required to run research.
MIN_RESEARCH_CONFIDENCE_MASS = 1.0


def _coerce_unit(v: Any) -> float:
    try:
        x = float(v)
    except (TypeError, ValueError):
        return 0.0
    if x != x:  # NaN
        return 0.0
    return max(0.0, min(1.0, x))


def _effective_item_confidence(raw: Any) -> float:
    c = _coerce_unit(raw)
    return c if c > 1e-6 else CONFIDENCE_FLOOR


def _score_merged_events(events: list[Any]) -> float:
    total = 0.0
    for ev in events:
        if not isinstance(ev, dict):
            continue
        if not (str(ev.get("event") or "").strip()):
            continue
        total += _effective_item_confidence(ev.get("confidence"))
    return total


def _score_structured_extras(structured_list: list[Any]) -> float:
    """
    Parties, claims, summary, jurisdiction, damages from this run's structured docs.
    Events are omitted — they are already counted in merged state['events'].
    """
    total = 0.0
    for doc in structured_list or []:
        if not isinstance(doc, dict):
            continue
        summary = doc.get("summary")
        if isinstance(summary, dict) and str(summary.get("text") or "").strip():
            total += _effective_item_confidence(summary.get("confidence"))

        for cl in doc.get("claims") or []:
            if isinstance(cl, dict) and str(cl.get("type") or "").strip():
                total += _effective_item_confidence(cl.get("confidence"))

        for p in doc.get("parties") or []:
            if isinstance(p, dict) and str(p.get("name") or "").strip():
                total += _effective_item_confidence(p.get("confidence"))

        j = doc.get("jurisdiction")
        if isinstance(j, dict) and str(j.get("value") or "").strip():
            total += _effective_item_confidence(j.get("confidence"))

        for d in doc.get("damages") or []:
            if isinstance(d, dict) and str(d.get("type") or "").strip():
                total += _effective_item_confidence(d.get("confidence"))

    return total


def research_context_confidence_score(state: CaseState) -> float:
    """Weighted sum of confidences over case events (merged) and non-event structured fields (this ingest)."""
    ev_score = _score_merged_events(state.get("events") or [])
    extra = _score_structured_extras(state.get("structured") or [])
    return ev_score + extra


def sufficient_context_for_research(state: CaseState) -> bool:
    return research_context_confidence_score(state) >= MIN_RESEARCH_CONFIDENCE_MASS


def should_run_initial_research(case_id: str, state: CaseState) -> bool:
    if read_pipeline_state(case_id).get("initial_research_completed"):
        return False
    return sufficient_context_for_research(state)
