"""
Build case timelines from events.json: date normalization, ordering,
deterministic conflict resolution (support score), persist timelines.json.

No imports from rag.router (safe from ingest_endpoint).
"""

from __future__ import annotations

import json
import math
import re
from datetime import datetime, timezone
from typing import Any, Callable

from dateutil import parser as date_parser

from storage import default_cases_root

from timeline_provenance import resolve_timeline_source

# Support score weights (deterministic v1)
W_CONFIDENCE = 1.0
W_SPAN_LOG = 0.15
W_DOC_CORROBORATION = 0.2

# Same calendar day + dissimilar event labels → conflict cluster
JACCARD_CONFLICT_THRESHOLD = 0.35

# Tie: if |score_a - score_b| < this, could branch (v1: still pick lexicographic)
SCORE_TIE_EPSILON = 1e-6


def empty_timeline_payload(case_id: str) -> dict[str, Any]:
    """Shape returned by the API when timelines.json is missing."""
    now = datetime.now(timezone.utc).isoformat()
    return {
        "version": 1,
        "case_id": case_id,
        "updated_at": now,
        "primary": {"entries": []},
        "conflicts": [],
        "branches": [],
    }


def _events_path(case_id: str):
    return default_cases_root() / case_id / "events.json"


def _timelines_path(case_id: str):
    return default_cases_root() / case_id / "timelines.json"


def read_case_events(case_id: str) -> list[dict[str, Any]]:
    p = _events_path(case_id)
    if not p.is_file():
        return []
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return []
    if not isinstance(data, list):
        return []
    return [e for e in data if isinstance(e, dict)]


def normalized_sort_date(date_val: str | None) -> str | None:
    """Return YYYY-MM-DD or None if unparseable."""
    if date_val is None:
        return None
    s = str(date_val).strip()
    if not s:
        return None
    # ISO-like already
    if re.match(r"^\d{4}-\d{2}-\d{2}$", s):
        return s
    try:
        dt = date_parser.parse(s, fuzzy=False)
        return dt.strftime("%Y-%m-%d")
    except (ValueError, TypeError, OverflowError):
        try:
            dt = date_parser.parse(s, fuzzy=True)
            return dt.strftime("%Y-%m-%d")
        except (ValueError, TypeError, OverflowError):
            return None


def token_jaccard(a: str, b: str) -> float:
    ta = set(re.findall(r"\w+", (a or "").lower()))
    tb = set(re.findall(r"\w+", (b or "").lower()))
    if not ta and not tb:
        return 1.0
    if not ta or not tb:
        return 0.0
    inter = len(ta & tb)
    union = len(ta | tb)
    return inter / union if union else 0.0


def support_score(ev: dict[str, Any], idx: int, all_events: list[dict[str, Any]]) -> float:
    try:
        conf = float(ev.get("confidence") or 0.0)
    except (TypeError, ValueError):
        conf = 0.0
    span = len((ev.get("source_span") or "").strip())
    doc_id = str(ev.get("doc_id") or "").strip()
    corroboration = 0
    if doc_id:
        for j, other in enumerate(all_events):
            if j == idx:
                continue
            if str(other.get("doc_id") or "").strip() == doc_id:
                corroboration += 1
    return (
        W_CONFIDENCE * conf
        + W_SPAN_LOG * math.log(1 + max(span, 0))
        + W_DOC_CORROBORATION * corroboration
    )


def _conflict_group_id(members: list[int]) -> str:
    """Stable id for a union-find cluster (for UI branch persistence)."""
    return "g-" + "-".join(str(x) for x in sorted(members))


def _entry_dict(
    case_id: str,
    events: list[dict[str, Any]],
    enriched: list[dict[str, Any]],
    i: int,
    *,
    conflict_id: str | None = None,
) -> dict[str, Any]:
    """One timeline card row (matches primary.entries item shape)."""
    row = enriched[i]
    ev = row["ev"]
    date_raw = ev.get("date")
    date_raw_s = str(date_raw).strip() if date_raw is not None else ""
    sort_d = row["sort_date"]
    title = str(ev.get("event") or "").strip() or "(event)"
    desc = str(ev.get("source_span") or "").strip()
    cxid = str(ev.get("context_id") or "").strip() or None
    out: dict[str, Any] = {
        "id": f"ev-{case_id}-{i}",
        "title": title,
        "description": desc,
        "date_display": date_raw_s or (sort_d or ""),
        "sort_date": sort_d,
        "doc_id": ev.get("doc_id"),
        "context_id": cxid,
        "source_span": ev.get("source_span"),
        "confidence": ev.get("confidence"),
        "support_score": round(row["score"], 6),
        "events_json_index": i,
    }
    if conflict_id is not None:
        out["conflict_id"] = conflict_id
    out["source_context"] = resolve_timeline_source(case_id, ev.get("doc_id"), cxid)
    return out


def _make_union_find(n: int) -> tuple[list[int], Callable[[int], int], Callable[[int, int], None]]:
    parent = list(range(n))

    def find(x: int) -> int:
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(a: int, b: int) -> None:
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[rb] = ra

    return parent, find, union


def build_timeline_payload(case_id: str, events: list[dict[str, Any]]) -> dict[str, Any]:
    """
    Full timelines.json body: primary entries, conflicts, branches (empty v1 unless tie policy).
    """
    now = datetime.now(timezone.utc).isoformat()
    n = len(events)
    if n == 0:
        out = empty_timeline_payload(case_id)
        out["updated_at"] = now
        return out

    enriched: list[dict[str, Any]] = []
    for i, ev in enumerate(events):
        sd = normalized_sort_date(ev.get("date") if isinstance(ev.get("date"), (str, type(None))) else str(ev.get("date") or ""))
        enriched.append(
            {
                "idx": i,
                "ev": ev,
                "sort_date": sd,
                "score": support_score(ev, i, events),
            }
        )

    parent, find, union = _make_union_find(n)
    for i in range(n):
        for j in range(i + 1, n):
            si, sj = enriched[i]["sort_date"], enriched[j]["sort_date"]
            if si is None or sj is None:
                continue
            if si != sj:
                continue
            ja = token_jaccard(
                str(enriched[i]["ev"].get("event") or ""),
                str(enriched[j]["ev"].get("event") or ""),
            )
            if ja < JACCARD_CONFLICT_THRESHOLD:
                union(i, j)

    groups: dict[int, list[int]] = {}
    for i in range(n):
        r = find(i)
        groups.setdefault(r, []).append(i)

    winners: set[int] = set()
    conflicts_out: list[dict[str, Any]] = []
    branches: list[dict[str, Any]] = []

    for _root, members in groups.items():
        if len(members) == 1:
            winners.add(members[0])
            continue
        members_sorted = sorted(
            members,
            key=lambda idx: (
                -enriched[idx]["score"],
                -len(str(events[idx].get("source_span") or "")),
                str(events[idx].get("event") or ""),
                idx,
            ),
        )
        w = members_sorted[0]
        winners.add(w)
        losers = members_sorted[1:]
        top_score = enriched[w]["score"]
        second_score = enriched[losers[0]]["score"] if losers else top_score
        needs_branch = abs(top_score - second_score) < SCORE_TIE_EPSILON and len(members_sorted) > 1
        if needs_branch:
            branches.append(
                {
                    "id": f"tie-{w}",
                    "reason": "equal_support_scores",
                    "candidate_indices": members_sorted,
                }
            )
        cg_id = _conflict_group_id(list(members))
        conflicts_out.append(
            {
                "conflict_id": cg_id,
                "winner_index": w,
                "loser_indices": losers,
                "reason": "conflict_resolved",
                "scores": {str(idx): round(enriched[idx]["score"], 6) for idx in members_sorted},
            }
        )

    primary_indices = sorted(winners)
    primary_rows = sorted(
        (enriched[i] for i in primary_indices),
        key=lambda row: (
            0 if row["sort_date"] else 1,
            row["sort_date"] or "",
            row["idx"],
        ),
    )

    entries: list[dict[str, Any]] = []
    for row in primary_rows:
        i = row["idx"]
        entries.append(_entry_dict(case_id, events, enriched, i))

    for c in conflicts_out:
        w = c["winner_index"]
        losers = c["loser_indices"]
        cg_id = c.get("conflict_id") or _conflict_group_id([w, *losers])
        for e in entries:
            if e.get("events_json_index") == w:
                e["conflict_id"] = cg_id
                e["alternates"] = [_entry_dict(case_id, events, enriched, li, conflict_id=cg_id) for li in losers]
                break

    from timeline_branch_llm import analyze_timeline_branch_conflict

    for e in entries:
        if e.get("alternates"):
            e["branch_llm"] = analyze_timeline_branch_conflict(case_id, e)

    return {
        "version": 1,
        "case_id": case_id,
        "updated_at": now,
        "primary": {"entries": entries},
        "conflicts": conflicts_out,
        "branches": branches,
    }


def write_timelines_json(case_id: str, payload: dict[str, Any]) -> None:
    p = _timelines_path(case_id)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def rebuild_case_timeline(case_id: str) -> dict[str, Any]:
    """Run the LangGraph timeline workflow: read events, merge conflicts, persist timelines.json."""
    from workflow.timeline_graph import run_timeline_workflow

    final = run_timeline_workflow(case_id)
    return final["timelines_payload"]


def read_timelines_json(case_id: str) -> dict[str, Any] | None:
    p = _timelines_path(case_id)
    if not p.is_file():
        return None
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None
    return data if isinstance(data, dict) else None
