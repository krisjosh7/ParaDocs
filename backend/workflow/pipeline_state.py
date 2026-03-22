"""Per-case flags for the LangGraph case pipeline (e.g. one-time auto-research)."""

from __future__ import annotations

import json
from typing import Any

from storage import default_cases_root

STATE_VERSION = 1


def _path(case_id: str):
    return default_cases_root() / case_id / "pipeline_state.json"


def read_pipeline_state(case_id: str) -> dict[str, Any]:
    p = _path(case_id)
    if not p.is_file():
        return {
            "version": STATE_VERSION,
            "initial_research_completed": False,
        }
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {
            "version": STATE_VERSION,
            "initial_research_completed": False,
        }
    if not isinstance(data, dict):
        return {
            "version": STATE_VERSION,
            "initial_research_completed": False,
        }
    out = dict(data)
    out.setdefault("version", STATE_VERSION)
    out.setdefault("initial_research_completed", False)
    return out


def mark_initial_research_completed(case_id: str) -> None:
    data = read_pipeline_state(case_id)
    data["version"] = STATE_VERSION
    data["initial_research_completed"] = True
    p = _path(case_id)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(data, indent=2), encoding="utf-8")
