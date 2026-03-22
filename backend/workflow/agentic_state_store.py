"""Persist agentic reasoning outputs per case: hypotheses, tasks, research_queries."""

from __future__ import annotations

import json
from typing import Any

from context_catalog import validate_case_id
from storage import default_cases_root

STATE_VERSION = 1


def _path(case_id: str):
    return default_cases_root() / case_id / "agentic_state.json"


def default_agentic_blob(case_id: str) -> dict[str, Any]:
    return {
        "version": STATE_VERSION,
        "case_id": case_id,
        "hypotheses": [],
        "tasks": [],
        "research_queries": [],
    }


def read_agentic_state(case_id: str) -> dict[str, Any]:
    validate_case_id(case_id)
    p = _path(case_id)
    if not p.is_file():
        return default_agentic_blob(case_id)
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return default_agentic_blob(case_id)
    if not isinstance(data, dict):
        return default_agentic_blob(case_id)
    out = default_agentic_blob(case_id)
    out["hypotheses"] = data["hypotheses"] if isinstance(data.get("hypotheses"), list) else []
    out["tasks"] = data["tasks"] if isinstance(data.get("tasks"), list) else []
    rq = data.get("research_queries")
    out["research_queries"] = rq if isinstance(rq, list) else []
    return out


def write_agentic_state(case_id: str, data: dict[str, Any]) -> None:
    validate_case_id(case_id)
    blob = default_agentic_blob(case_id)
    if isinstance(data.get("hypotheses"), list):
        blob["hypotheses"] = data["hypotheses"]
    if isinstance(data.get("tasks"), list):
        blob["tasks"] = data["tasks"]
    if isinstance(data.get("research_queries"), list):
        blob["research_queries"] = data["research_queries"]
    p = _path(case_id)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(blob, indent=2), encoding="utf-8")
