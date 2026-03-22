"""
LLM comparison for same-day conflicting timeline narratives (fork branches).

Disabled when PARADOCS_TIMELINE_BRANCH_LLM is 0/false/no or when the API fails.
"""

from __future__ import annotations

import json
import logging
import os
from typing import Any

from groq_llm import generate_json

_logger = logging.getLogger(__name__)

_BRANCH_SYSTEM = """You are a legal case assistant. Multiple event descriptions share the same calendar day but describe different facts (they may both be valid perspectives from different documents).

Compare them neutrally. Do not invent facts beyond the given text.

Return STRICT JSON only with this shape (no markdown):
{
  "comparison_summary": "2–5 sentences explaining how the accounts differ and what each emphasizes.",
  "suggested_events_json_index": <integer or null>,
  "notes": "optional short note for the attorney, or empty string"
}

Rules for suggested_events_json_index:
- It MUST be exactly one of the integer indices listed in the user message under "Candidate" lines, OR null if neither is clearly more reliable from the text alone.
- Prefer slightly more specific, source-grounded spans over vague labels when tied.
- Do not use any index not listed in the user message.
"""


def _branch_llm_enabled() -> bool:
    v = os.environ.get("PARADOCS_TIMELINE_BRANCH_LLM", "1").strip().lower()
    return v not in ("0", "false", "no", "off")


def analyze_timeline_branch_conflict(case_id: str, primary_entry: dict[str, Any]) -> dict[str, Any]:
    """
    primary_entry: winning timeline row with alternates[], sort_date, events_json_index, title, description, support_score, doc_id.
    Returns branch_llm object for JSON/API (never raises).
    """
    base_out: dict[str, Any] = {
        "comparison_summary": "",
        "suggested_events_json_index": None,
        "notes": "",
        "skipped": False,
        "model_error": None,
    }

    if not _branch_llm_enabled():
        base_out["skipped"] = True
        return base_out

    alternates = primary_entry.get("alternates") or []
    if not alternates:
        base_out["skipped"] = True
        return base_out

    candidates: list[dict[str, Any]] = [
        {
            "events_json_index": primary_entry["events_json_index"],
            "event": primary_entry.get("title") or "",
            "source_span": primary_entry.get("description") or "",
            "support_score": primary_entry.get("support_score"),
            "doc_id": primary_entry.get("doc_id"),
        }
    ]
    for a in alternates:
        candidates.append(
            {
                "events_json_index": a["events_json_index"],
                "event": a.get("title") or "",
                "source_span": a.get("description") or "",
                "support_score": a.get("support_score"),
                "doc_id": a.get("doc_id"),
            }
        )

    valid_indices = {c["events_json_index"] for c in candidates}
    sort_date = primary_entry.get("sort_date") or ""

    lines = [
        f"case_id={case_id}",
        f"sort_date={sort_date}",
        "Candidates (events_json_index is the stable id; deterministic scores are heuristic only):",
    ]
    for c in candidates:
        lines.append(
            f"- Candidate events_json_index={c['events_json_index']!r}: "
            f"event_label={c['event']!r} "
            f"support_score={c['support_score']!r} "
            f"doc_id={c['doc_id']!r}\n"
            f"  source_span: {c['source_span']!r}"
        )

    user_text = "\n".join(lines)

    try:
        raw = generate_json(_BRANCH_SYSTEM, user_text)
        data = json.loads(raw)
    except Exception as exc:
        _logger.warning("Timeline branch LLM failed for case_id=%s: %s", case_id, exc)
        base_out["model_error"] = str(exc)
        return base_out

    if not isinstance(data, dict):
        base_out["model_error"] = "LLM returned non-object JSON"
        return base_out

    summary = str(data.get("comparison_summary") or "").strip()
    notes = str(data.get("notes") or "").strip()
    suggested = data.get("suggested_events_json_index")
    if suggested is not None:
        try:
            suggested = int(suggested)
        except (TypeError, ValueError):
            suggested = None
        if suggested is not None and suggested not in valid_indices:
            suggested = None

    base_out["comparison_summary"] = summary
    base_out["notes"] = notes
    base_out["suggested_events_json_index"] = suggested
    return base_out
