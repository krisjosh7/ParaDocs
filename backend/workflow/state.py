from __future__ import annotations

from typing import TypedDict


class CaseState(TypedDict):
    case_id: str
    raw_text: str
    source: str  # "upload" | "tts" | "web"
    context_id: str | None  # Discovery catalog row id when ingest is from context library

    documents: list  # accumulated Document dicts with doc_id, summary, etc.
    structured: list  # accumulated StructuredDocument dicts
    events: list  # extracted + normalized Event dicts

    # Phase 2: full timelines.json payload after rebuild_timeline node
    timelines: dict
    conflicts: list  # reserved
    # Phase 3: research_subgraph output (all_stored_results) + metadata
    research_results: list
    research_stop_reason: str | None
    research_iteration: int
    # Phase 4: date backfill + optional timeline refresh after timeline/research
    reasoning_backfill_changes: int
    reasoning_timeline_refreshed: bool
    hypotheses: list
    tasks: list
    # Agentic reasoning: suggested web/search queries (not executed here)
    research_queries: list


def initial_case_state(
    case_id: str, raw_text: str, source: str = "upload", *, context_id: str | None = None
) -> CaseState:
    """Default state for a single-document run of the case pipeline (Phases 1–3)."""
    return {
        "case_id": case_id,
        "raw_text": raw_text,
        "source": source,
        "context_id": (context_id.strip() if isinstance(context_id, str) and context_id.strip() else None),
        "documents": [],
        "structured": [],
        "events": [],
        "timelines": {},
        "conflicts": [],
        "research_results": [],
        "research_stop_reason": None,
        "research_iteration": 0,
        "reasoning_backfill_changes": 0,
        "reasoning_timeline_refreshed": False,
        "hypotheses": [],
        "tasks": [],
        "research_queries": [],
    }
