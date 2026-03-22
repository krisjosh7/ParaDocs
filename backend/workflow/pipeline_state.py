"""Per-case flags for the LangGraph case pipeline (e.g. one-time auto-research)."""

from __future__ import annotations

import json
from typing import Any

from storage import default_cases_root

STATE_VERSION = 1


def _path(case_id: str):
    return default_cases_root() / case_id / "pipeline_state.json"


def _defaults() -> dict[str, Any]:
    return {
        "version": STATE_VERSION,
        "initial_research_completed": False,
        "reasoning_mode": "normal",
        "last_agentic_run_at": None,
        "last_content_fingerprint": "",
        "agentic_run_timestamps": [],
        "agentic_hour_bucket": "",
        "agentic_runs_this_hour": 0,
        "reasoning_stale": False,
        "stale_reason": "",
        "task_execution_mode": "manual",
        "last_task_execution_at": None,
        "task_exec_hour_bucket": "",
        "task_exec_runs_this_hour": 0,
    }


def read_pipeline_state(case_id: str) -> dict[str, Any]:
    p = _path(case_id)
    base = _defaults()
    if not p.is_file():
        return dict(base)
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return dict(base)
    if not isinstance(data, dict):
        return dict(base)
    out = {**base, **data}
    out.setdefault("version", STATE_VERSION)
    out.setdefault("initial_research_completed", False)
    out.setdefault("reasoning_mode", "normal")
    out.setdefault("agentic_run_timestamps", [])
    out.setdefault("task_execution_mode", "manual")
    return out


def merge_pipeline_state(case_id: str, updates: dict[str, Any]) -> None:
    """Merge ``updates`` into pipeline_state.json (creates file if missing)."""
    data = read_pipeline_state(case_id)
    for k, v in updates.items():
        data[k] = v
    data["version"] = STATE_VERSION
    p = _path(case_id)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(data, indent=2), encoding="utf-8")


def mark_initial_research_completed(case_id: str) -> None:
    merge_pipeline_state(case_id, {"initial_research_completed": True})
