"""
Lightweight task execution: RAG over the case + a short LLM summary (separate from full agentic JSON).

Token-conscious: small top_k, capped excerpt chars, low max_completion_tokens, per-case rate limits.
"""

from __future__ import annotations

import logging
import queue
import threading
import time
from datetime import datetime, timezone
from itertools import count
from typing import Any, Literal

from context_catalog import validate_case_id

from groq_llm import generate_text
from rag.vector_store import query_case
from workflow.agentic_state_store import read_agentic_state, write_agentic_state
from workflow.pipeline_state import merge_pipeline_state, read_pipeline_state

_logger = logging.getLogger(__name__)

TASK_EXECUTION_MODES = frozenset({"manual", "auto_light"})

_job_queue: queue.PriorityQueue[tuple[int, int, str, int, bool]] = queue.PriorityQueue()
_seq = count()
_worker_thread: threading.Thread | None = None
_worker_start_lock = threading.Lock()
_case_exec_locks: dict[str, threading.Lock] = {}
_case_exec_locks_guard = threading.Lock()

_global_exec_times: list[float] = []
_global_exec_lock = threading.Lock()

TASK_EXEC_SYSTEM = """You help with a legal case task using only the EXCERPTS provided.

Rules:
- Answer in 2–5 short bullet lines, each starting with "- ".
- If excerpts do not address the task, say so in one bullet; do not invent facts.
- When citing, mention the doc_id shown in brackets in the excerpts.
- No markdown headings; keep under ~120 words."""

_DONE_STATUS_TOKENS = frozenset(
    {"done", "complete", "completed", "resolved", "closed"}
)


def _env_int(name: str, default: int) -> int:
    import os

    raw = os.environ.get(name, "").strip()
    if not raw:
        return default
    try:
        return max(0, int(raw))
    except ValueError:
        return default


def _env_float(name: str, default: float) -> float:
    import os

    raw = os.environ.get(name, "").strip()
    if not raw:
        return default
    try:
        return float(raw)
    except ValueError:
        return default


def _norm_status(raw: Any) -> str:
    x = str(raw or "").strip().lower().replace("-", "_").replace(" ", "_")
    if x in _DONE_STATUS_TOKENS:
        return "done"
    if x in ("in_progress", "inprogress", "active", "doing", "started"):
        return "in_progress"
    return "upcoming"


def _case_lock(case_id: str) -> threading.Lock:
    with _case_exec_locks_guard:
        return _case_exec_locks.setdefault(case_id, threading.Lock())


def _global_exec_slot_available() -> bool:
    cap = _env_int("TASK_EXEC_GLOBAL_MAX_PER_MINUTE", 12)
    if cap <= 0:
        return True
    now = time.monotonic()
    with _global_exec_lock:
        cutoff = now - 60.0
        pruned = [t for t in _global_exec_times if t >= cutoff]
        _global_exec_times[:] = pruned
        return len(_global_exec_times) < cap


def _global_exec_commit() -> None:
    with _global_exec_lock:
        _global_exec_times.append(time.monotonic())


def _budget_allows_run(case_id: str, *, force_bypass_cooldown: bool) -> Literal["ok", "interval", "hourly", "global"]:
    ps = read_pipeline_state(case_id)
    now = datetime.now(timezone.utc)

    if not _global_exec_slot_available():
        return "global"

    if not force_bypass_cooldown:
        last_raw = ps.get("last_task_execution_at")
        if last_raw:
            try:
                last_run = datetime.fromisoformat(str(last_raw).replace("Z", "+00:00"))
                delta = (now - last_run.astimezone(timezone.utc)).total_seconds()
                need = _env_float("TASK_EXEC_MIN_INTERVAL_SECONDS", 45.0)
                if delta < need:
                    return "interval"
            except (ValueError, TypeError):
                pass

    hour_key = now.strftime("%Y%m%d%H")
    hour_bucket = str(ps.get("task_exec_hour_bucket") or "")
    runs_in_hour = int(ps.get("task_exec_runs_this_hour") or 0) if hour_bucket == hour_key else 0
    max_h = max(1, _env_int("TASK_EXEC_MAX_PER_CASE_PER_HOUR", 24))
    if not force_bypass_cooldown and runs_in_hour >= max_h:
        return "hourly"

    return "ok"


def _commit_budget_after_run(case_id: str) -> None:
    now = datetime.now(timezone.utc)
    hour_key = now.strftime("%Y%m%d%H")
    ps = read_pipeline_state(case_id)
    hour_bucket = str(ps.get("task_exec_hour_bucket") or "")
    runs_in_hour = int(ps.get("task_exec_runs_this_hour") or 0) if hour_bucket == hour_key else 0
    merge_pipeline_state(
        case_id,
        {
            "last_task_execution_at": now.isoformat(),
            "task_exec_hour_bucket": hour_key,
            "task_exec_runs_this_hour": runs_in_hour + 1,
        },
    )
    _global_exec_commit()


def task_execution_auto_enabled(case_id: str) -> bool:
    ps = read_pipeline_state(case_id)
    mode = str(ps.get("task_execution_mode") or "manual").strip().lower()
    return mode == "auto_light"


def _task_skipped_for_manual_only(t: dict[str, Any]) -> bool:
    if str(t.get("source") or "").strip() != "user":
        return False
    typ = str(t.get("type") or "").strip().lower()
    return typ == "execution"


def _task_eligible(
    t: dict[str, Any],
    *,
    task_id: str | None,
    force_rerun: bool,
) -> bool:
    tid = str(t.get("id") or "").strip()
    if task_id is not None:
        if tid != str(task_id).strip():
            return False
    if _task_skipped_for_manual_only(t):
        return False
    st = _norm_status(t.get("status"))
    if st == "done" and not force_rerun:
        return False
    return True


def _build_excerpt_block(hits: list[dict[str, Any]], *, max_chars: int) -> str:
    parts: list[str] = []
    used = 0
    for h in hits:
        md = h.get("metadata") or {}
        doc_id = str(md.get("doc_id") or h.get("id") or "").strip() or "unknown"
        body = str(h.get("document") or "").strip()
        if not body:
            continue
        line = f"[{doc_id}] {body}\n"
        if used + len(line) > max_chars:
            remain = max_chars - used
            if remain > 80:
                parts.append(line[:remain] + "…\n")
            break
        parts.append(line)
        used += len(line)
    return "".join(parts).strip()


def _run_single_task(
    case_id: str,
    task: dict[str, Any],
    *,
    force_rerun: bool,
) -> dict[str, Any]:
    tid = str(task.get("id") or "").strip()
    title = str(task.get("task") or "").strip()
    reason = str(task.get("reason") or "").strip()
    if not tid or not title:
        return {"task_id": tid, "ok": False, "error": "missing id or task text"}

    top_k = max(1, min(_env_int("TASK_EXEC_TOP_K", 5), 12))
    max_ctx = max(2000, _env_int("TASK_EXEC_MAX_CONTEXT_CHARS", 14_000))
    max_out = max(64, min(_env_int("TASK_EXEC_MAX_OUTPUT_TOKENS", 384), 1024))

    q = title if len(title) <= 500 else title[:500] + "…"
    if reason and len(reason) < 400:
        q = f"{q}\n{reason}"

    task["status"] = "in_progress"
    task.pop("execution_error", None)

    try:
        hits = query_case(case_id, q, top_k=top_k)
    except Exception:
        _logger.exception("task_exec query_case failed case_id=%s task_id=%s", case_id, tid)
        task["status"] = "upcoming"
        task["execution_error"] = "RAG query failed"
        return {"task_id": tid, "ok": False, "error": "rag_failed"}

    excerpt = _build_excerpt_block(hits, max_chars=max_ctx)
    if not excerpt:
        task["status"] = "done"
        task["execution_summary"] = (
            "No indexed case excerpts matched this task. Add or re-index documents in Discovery, then run again."
        )
        task["executed_at"] = datetime.now(timezone.utc).isoformat()
        task.pop("execution_error", None)
        return {"task_id": tid, "ok": True, "skipped_llm": True}

    user_payload = f"TASK:\n{title}\n\nREASON:\n{reason or '(none)'}\n\nEXCERPTS:\n{excerpt}\n"
    try:
        summary = generate_text(
            TASK_EXEC_SYSTEM,
            user_payload,
            temperature=0.2,
            max_completion_tokens=max_out,
        ).strip()
    except Exception as e:
        _logger.exception("task_exec LLM failed case_id=%s task_id=%s", case_id, tid)
        task["status"] = "upcoming"
        task["execution_error"] = str(e)[:500]
        return {"task_id": tid, "ok": False, "error": "llm_failed"}

    task["status"] = "done"
    task["execution_summary"] = summary[:8000]
    task["executed_at"] = datetime.now(timezone.utc).isoformat()
    task.pop("execution_error", None)
    return {"task_id": tid, "ok": True}


def execute_tasks_light(
    case_id: str,
    *,
    task_id: str | None = None,
    max_tasks: int = 1,
    force_bypass_cooldown: bool = False,
    force_rerun: bool = False,
) -> dict[str, Any]:
    """
    Run up to ``max_tasks`` tasks (specific ``task_id`` or next eligible). Updates agentic_state on disk.
    Respects per-case and global rate limits unless ``force_bypass_cooldown`` (e.g. explicit user click).
    """
    cid = validate_case_id(case_id)
    max_tasks = max(1, min(int(max_tasks), 5))

    with _case_lock(cid):
        blob = read_agentic_state(cid)
        tasks = blob.get("tasks")
        if not isinstance(tasks, list):
            return {"ran": 0, "results": [], "skipped": "no_tasks"}

        indices: list[int] = []
        if task_id is not None:
            want = str(task_id).strip()
            for i, raw in enumerate(tasks):
                if not isinstance(raw, dict):
                    continue
                if str(raw.get("id") or "").strip() == want and _task_eligible(
                    dict(raw), task_id=want, force_rerun=force_rerun
                ):
                    indices.append(i)
                    break
        else:
            for i, raw in enumerate(tasks):
                if len(indices) >= max_tasks:
                    break
                if not isinstance(raw, dict):
                    continue
                if _task_eligible(dict(raw), task_id=None, force_rerun=force_rerun):
                    indices.append(i)

        if not indices:
            return {"ran": 0, "results": [], "skipped": "no_eligible_task"}

        results: list[dict[str, Any]] = []
        ran = 0
        for n_done, idx in enumerate(indices):
            bc = force_bypass_cooldown or n_done > 0
            budget = _budget_allows_run(cid, force_bypass_cooldown=bc)
            if budget != "ok":
                results.append(
                    {
                        "task_id": str((tasks[idx] or {}).get("id") or ""),
                        "ok": False,
                        "error": f"budget:{budget}",
                    }
                )
                break
            t = dict(tasks[idx])
            out = _run_single_task(cid, t, force_rerun=force_rerun)
            tasks[idx] = t
            results.append(out)
            if out.get("ok"):
                ran += 1
            _commit_budget_after_run(cid)

        blob["tasks"] = tasks
        write_agentic_state(cid, blob)

    return {"ran": ran, "results": results, "skipped": None}


def enqueue_task_execution_job(
    case_id: str,
    *,
    max_tasks: int = 1,
    force_bypass_cooldown: bool = False,
    priority: int = 0,
) -> None:
    try:
        validate_case_id(case_id)
    except ValueError:
        return
    _job_queue.put((-priority, next(_seq), case_id, max_tasks, force_bypass_cooldown))


def maybe_enqueue_after_reasoning(case_id: str) -> None:
    if not task_execution_auto_enabled(case_id):
        return
    enqueue_task_execution_job(case_id, max_tasks=1, force_bypass_cooldown=False, priority=0)


def _worker_loop() -> None:
    while True:
        try:
            _neg_pri, _seqn, case_id, max_tasks, force_bc = _job_queue.get(timeout=1.0)
        except queue.Empty:
            continue
        try:
            execute_tasks_light(
                case_id,
                task_id=None,
                max_tasks=max_tasks,
                force_bypass_cooldown=force_bc,
                force_rerun=False,
            )
        except Exception:
            _logger.exception("task execution worker error case_id=%s", case_id)
        finally:
            _job_queue.task_done()


def start_task_execution_worker() -> None:
    global _worker_thread
    with _worker_start_lock:
        if _worker_thread is not None and _worker_thread.is_alive():
            return
        t = threading.Thread(target=_worker_loop, daemon=True, name="paradocs-task-exec")
        t.start()
        _worker_thread = t
        _logger.info("Task execution worker started")
