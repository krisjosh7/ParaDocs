"""
Persist cumulative research stats per case under cases/{case_id}/research_summary.json.

Used to surface a running total of distinct stored sources (cluster ids) on the case dashboard.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from context_catalog import validate_case_id
from storage import default_cases_root

SUMMARY_VERSION = 1


def _path(case_id: str):
    return default_cases_root() / case_id / "research_summary.json"


def _default(case_id: str) -> dict[str, Any]:
    return {
        "version": SUMMARY_VERSION,
        "case_id": case_id,
        "unique_sources_count": 0,
        "total_runs": 0,
        "seen_cluster_ids": [],
        "last_run": None,
    }


def read_raw(case_id: str) -> dict[str, Any]:
    p = _path(case_id)
    if not p.is_file():
        return _default(case_id)
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return _default(case_id)
    if not isinstance(data, dict):
        return _default(case_id)
    return data


def record_research_run(
    case_id: str,
    all_stored_results: list[dict],
    stop_reason: str | None,
    iteration: int,
) -> dict[str, Any]:
    """Merge a completed research graph run into on-disk summary. Returns updated raw dict."""
    validate_case_id(case_id)
    data = read_raw(case_id)
    seen = list(dict.fromkeys(data.get("seen_cluster_ids") or []))
    seen_set = set(seen)
    added_unique = 0
    for r in all_stored_results:
        if not isinstance(r, dict):
            continue
        rid = str(r.get("id") or "").strip()
        if rid and rid not in seen_set:
            seen_set.add(rid)
            seen.append(rid)
            added_unique += 1

    data["seen_cluster_ids"] = seen
    data["unique_sources_count"] = len(seen_set)
    data["total_runs"] = int(data.get("total_runs") or 0) + 1
    data["last_run"] = {
        "at": datetime.now(timezone.utc).isoformat(),
        "added_unique_this_run": added_unique,
        "batch_stored_count": len(all_stored_results),
        "stop_reason": (stop_reason or "") or "",
        "iteration": int(iteration or 0),
    }

    out_path = _path(case_id)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(data, indent=2), encoding="utf-8")
    return data


def public_summary(case_id: str) -> dict[str, Any]:
    """API-safe shape (no large internal lists)."""
    validate_case_id(case_id)
    data = read_raw(case_id)
    lr = data.get("last_run") if isinstance(data.get("last_run"), dict) else None
    return {
        "case_id": case_id,
        "unique_sources_count": int(data.get("unique_sources_count") or 0),
        "total_runs": int(data.get("total_runs") or 0),
        "last_run_at": lr.get("at") if lr else None,
        "last_run_added_unique": lr.get("added_unique_this_run") if lr else None,
        "last_batch_stored_count": lr.get("batch_stored_count") if lr else None,
        "last_stop_reason": (lr.get("stop_reason") or None) if lr else None,
        "last_iteration": lr.get("iteration") if lr else None,
    }
