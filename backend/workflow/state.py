from __future__ import annotations

from typing import TypedDict


class CaseState(TypedDict):
    case_id: str
    raw_text: str
    source: str  # "upload" | "tts" | "web"

    documents: list  # accumulated Document dicts with doc_id, summary, etc.
    structured: list  # accumulated StructuredDocument dicts
    events: list  # extracted + normalized Event dicts

    # Phase 2-4 placeholders (pass-through for now)
    timelines: dict
    conflicts: list
    research_results: list
    hypotheses: list
    tasks: list
