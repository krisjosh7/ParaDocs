"""
Agentic reasoning: hypotheses, actionable tasks, and suggested research queries.

Invoked by ``workflow.reasoning_agent.try_run_agentic`` (background worker / gated paths),
not by the LangGraph pipeline tail.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from groq_llm import generate_json
from timeline_logic import read_case_events, read_timelines_json
from workflow.agentic_state_store import read_agentic_state, write_agentic_state
from workflow.state import CaseState, initial_case_state

_logger = logging.getLogger(__name__)

_MAX_CONTEXT_CHARS = 48_000

AGENTIC_SYSTEM = """You are a legal case reasoning engine. You receive JSON describing events, timelines (including conflicts and branches), optional research findings, and existing hypotheses/tasks.

Output a single JSON object with exactly these keys:
- "hypotheses": array of objects. Each object may include: "id" (string), "theory" (string, the claim), "supporting_event_refs" (array of strings: event ids, timeline entry ids, or short quotes tying to the input), "timeline_label" (string: e.g. "primary" or a branch name from the input), "confidence" (number from 0 to 1).
- "tasks": array of objects. Each must be specific and actionable. Fields: "id" (string), "task" (string), "reason" (string: why this task exists), "source" must be one of: "missing_info", "conflict", "weak_evidence", "research_gap", "agent". Optional: "type", "priority", "status", "parent_task_id" (for subtasks when decomposing). Never set "source" to "user" — the system preserves user tasks separately.
- "research_queries": array of short plain-text search queries the case team could run elsewhere; do not claim you ran them.

Rules:
- Ground hypotheses in the supplied events/timelines; cite refs that appear in the input when possible.
- Propose tasks only for missing information, unresolved conflicts, weakly supported points, research gaps, or decomposition of complex work already implied by existing tasks.
- If timelines list multiple branches, align hypotheses to the appropriate timeline_label.

Return only valid JSON, no markdown."""

TASK_CLASSIFY_SYSTEM = """You classify whether a user message is an instruction assigning work to the legal case agent (something to do, find, build, or investigate for the case) versus a normal question or chat.

Output a single JSON object:
- "is_agent_task": boolean — true if the user is assigning a task (e.g. "Find...", "Figure out...", "Build...", "Investigate...", "Research...", "Determine whether...") rather than only asking for an immediate conversational answer.
- "task": if is_agent_task is true, an object with keys: "task" (string, imperative description), "type" (one of: "execution", "research", "investigation"), "priority" (e.g. "low", "medium", "high"), "status" (use "pending"). If is_agent_task is false, use null.

Return only valid JSON."""


def _norm_item_id(item: Any) -> str:
    if isinstance(item, dict):
        return str(item.get("id") or "").strip()
    return ""


def _merge_lists(disk_list: list[Any], state_list: list[Any]) -> list[Any]:
    out: list[Any] = list(disk_list) if isinstance(disk_list, list) else []
    seen = {_norm_item_id(x) for x in out if _norm_item_id(x)}
    for x in state_list or []:
        nid = _norm_item_id(x)
        if nid and nid in seen:
            continue
        if nid:
            seen.add(nid)
        out.append(x)
    return out


def _compact_research(results: list[Any], *, limit: int = 40) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for r in (results or [])[:limit]:
        if not isinstance(r, dict):
            continue
        slim: dict[str, Any] = {}
        for k in (
            "id",
            "title",
            "snippet",
            "url",
            "query",
            "score",
            "rag_doc_id",
            "cluster_id",
        ):
            if k in r and r[k] is not None:
                slim[k] = r[k]
        if slim:
            out.append(slim)
    return out


def _build_llm_user_payload(state: CaseState, merged: dict[str, list[Any]]) -> str:
    events = state.get("events") or []
    timelines = state.get("timelines") or {}
    if not timelines:
        cid = state.get("case_id") or ""
        if cid:
            loaded = read_timelines_json(cid)
            if loaded:
                timelines = loaded

    ctx = {
        "events": events,
        "timelines": timelines,
        "research_results": _compact_research(state.get("research_results") or []),
        "existing_hypotheses": merged["hypotheses"],
        "existing_tasks": merged["tasks"],
        "prior_research_queries": merged["research_queries"],
    }
    raw = json.dumps(ctx, indent=2, default=str)
    if len(raw) > _MAX_CONTEXT_CHARS:
        raw = raw[:_MAX_CONTEXT_CHARS] + "\n... (truncated)"
    return raw


def _merge_tasks_keep_user(prior_merged_tasks: list[Any], model_tasks: list[Any]) -> list[dict[str, Any]]:
    user_tasks = [
        t
        for t in prior_merged_tasks
        if isinstance(t, dict) and str(t.get("source") or "").strip() == "user"
    ]
    user_ids = {str(t.get("id") or "").strip() for t in user_tasks if t.get("id")}
    prior_agent_by_id: dict[str, dict[str, Any]] = {}
    for t in prior_merged_tasks or []:
        if not isinstance(t, dict) or str(t.get("source") or "").strip() == "user":
            continue
        aid = str(t.get("id") or "").strip()
        if aid:
            prior_agent_by_id[aid] = dict(t)

    merged: list[dict[str, Any]] = [dict(t) for t in user_tasks]
    for t in model_tasks or []:
        if not isinstance(t, dict):
            continue
        if str(t.get("source") or "").strip() == "user":
            continue
        tid = str(t.get("id") or "").strip()
        if tid and tid in user_ids:
            continue
        new = dict(t)
        if tid and tid in prior_agent_by_id:
            old = prior_agent_by_id[tid]
            for k in ("execution_summary", "executed_at", "execution_error"):
                if old.get(k):
                    new[k] = old[k]
            ost = str(old.get("status") or "").lower().replace("-", "_").replace(" ", "_")
            if ost in ("done", "complete", "completed", "resolved", "closed"):
                nst = str(new.get("status") or "").strip().lower().replace("-", "_").replace(" ", "_")
                if not nst or nst in ("pending", "upcoming"):
                    new["status"] = old.get("status")
        merged.append(new)
    return merged


def run_agentic_reasoning(case_id: str, state: CaseState) -> dict[str, Any]:
    """
    Load persisted agentic state, merge with ``state``, call LLM, persist, return
    LangGraph partial update keys: hypotheses, tasks, research_queries.
    On failure, returns {} so the graph does not break.
    """
    try:
        disk = read_agentic_state(case_id)
    except ValueError:
        _logger.warning("agentic_reasoning: invalid case_id=%s", case_id)
        return {}

    merged = {
        "hypotheses": _merge_lists(disk["hypotheses"], state.get("hypotheses") or []),
        "tasks": _merge_lists(disk["tasks"], state.get("tasks") or []),
        "research_queries": _merge_lists(
            disk["research_queries"], state.get("research_queries") or []
        ),
    }

    user_payload = _build_llm_user_payload(state, merged)

    try:
        raw = generate_json(AGENTIC_SYSTEM, user_payload)
        data = json.loads(raw)
    except (json.JSONDecodeError, TypeError, RuntimeError) as e:
        _logger.warning("agentic_reasoning: LLM or JSON failed case_id=%s: %s", case_id, e)
        return {}
    except Exception:
        _logger.exception("agentic_reasoning: unexpected error case_id=%s", case_id)
        return {}

    if not isinstance(data, dict):
        return {}

    hypotheses = data.get("hypotheses")
    if not isinstance(hypotheses, list):
        hypotheses = []

    rq_raw = data.get("research_queries")
    research_queries: list[str] = []
    if isinstance(rq_raw, list):
        for q in rq_raw:
            if isinstance(q, str) and q.strip():
                research_queries.append(q.strip())

    model_tasks = data.get("tasks")
    if not isinstance(model_tasks, list):
        model_tasks = []

    tasks_out = _merge_tasks_keep_user(merged["tasks"], model_tasks)

    out = {
        "hypotheses": hypotheses,
        "tasks": tasks_out,
        "research_queries": research_queries,
    }
    try:
        write_agentic_state(case_id, out)
    except Exception:
        _logger.exception("agentic_reasoning: persist failed case_id=%s", case_id)
    return out


def agentic_reasoning_node(state: CaseState) -> dict[str, Any]:
    return run_agentic_reasoning(state["case_id"], state)


def classify_user_message_as_task(user_message: str) -> tuple[bool, dict[str, Any] | None]:
    """
    Returns (is_agent_task, task_dict_or_none). On any failure, returns (False, None).
    """
    text = (user_message or "").strip()
    if not text:
        return False, None
    try:
        raw = generate_json(TASK_CLASSIFY_SYSTEM, text)
        data = json.loads(raw)
    except Exception:
        _logger.exception("task classify: LLM/JSON failed")
        return False, None
    if not isinstance(data, dict):
        return False, None
    if not data.get("is_agent_task"):
        return False, None
    task = data.get("task")
    if not isinstance(task, dict):
        return False, None
    return True, task


def build_case_state_snapshot_for_agentic(case_id: str) -> CaseState:
    """Minimal CaseState from disk for chat-triggered agentic runs."""
    st: CaseState = initial_case_state(case_id, "", "upload")
    st["events"] = read_case_events(case_id)
    tl = read_timelines_json(case_id)
    st["timelines"] = tl if isinstance(tl, dict) else {}
    st["research_results"] = []
    blob = read_agentic_state(case_id)
    st["hypotheses"] = list(blob["hypotheses"])
    st["tasks"] = list(blob["tasks"])
    st["research_queries"] = list(blob["research_queries"])
    return st
