"""
Bounded background agentic reasoning: queue jobs, enforce cooldowns and fingerprints.

Full LLM reasoning runs here (and via try_run_agentic with force for chat), not on the LangGraph tail.
"""

from __future__ import annotations

import hashlib
import logging
import os
import queue
import threading
import time
from datetime import datetime, timezone
from itertools import count
from typing import Literal

from context_catalog import validate_case_id

from workflow.agentic_state_store import read_agentic_state
from workflow.nodes.agentic_reasoning import build_case_state_snapshot_for_agentic, run_agentic_reasoning
from workflow.pipeline_state import merge_pipeline_state, read_pipeline_state

_logger = logging.getLogger(__name__)

_job_queue: queue.PriorityQueue[tuple[int, int, str, str, bool]] = queue.PriorityQueue()
_seq = count()
_worker_thread: threading.Thread | None = None
_worker_start_lock = threading.Lock()

REASONING_MODES = frozenset({"off", "normal", "aggressive"})


def _env_float(name: str, default: float) -> float:
    raw = os.environ.get(name, "").strip()
    if not raw:
        return default
    try:
        return float(raw)
    except ValueError:
        return default


def _env_int(name: str, default: int) -> int:
    raw = os.environ.get(name, "").strip()
    if not raw:
        return default
    try:
        n = int(raw)
    except ValueError:
        return default
    return max(0, n)


def min_interval_seconds_for_mode(mode: str) -> float:
    base = _env_float("AGENTIC_MIN_INTERVAL_SECONDS", 120.0)
    if mode == "aggressive":
        return max(30.0, base * 0.5)
    return max(15.0, base)


def max_runs_per_hour_for_mode(mode: str) -> int:
    base = _env_int("AGENTIC_MAX_RUNS_PER_CASE_PER_HOUR", 4)
    if mode == "aggressive":
        return max(1, base * 2)
    return max(1, base)


_global_run_times: list[float] = []
_global_lock = threading.Lock()


def _global_slot_available() -> bool:
    cap = _env_int("AGENTIC_GLOBAL_MAX_RUNS_PER_MINUTE", 8)
    if cap <= 0:
        return True
    now = time.monotonic()
    with _global_lock:
        cutoff = now - 60.0
        pruned = [t for t in _global_run_times if t >= cutoff]
        _global_run_times[:] = pruned
        return len(_global_run_times) < cap


def _global_slot_commit() -> None:
    with _global_lock:
        _global_run_times.append(time.monotonic())


def case_content_fingerprint(case_id: str) -> str:
    """Cheap change detector for skipping redundant agentic LLM runs."""
    from storage import default_cases_root

    base = default_cases_root() / case_id
    parts: list[str] = []

    for name in ("events.json", "timelines.json"):
        p = base / name
        if p.is_file():
            try:
                st = p.stat()
                parts.append(f"{name}:{st.st_mtime_ns}:{st.st_size}")
            except OSError:
                parts.append(f"{name}:missing")
        else:
            parts.append(f"{name}:missing")

    rs = base / "research_summary.json"
    if rs.is_file():
        try:
            raw = rs.read_bytes()
            parts.append("rs:" + hashlib.sha256(raw).hexdigest()[:16])
        except OSError:
            parts.append("rs:err")
    else:
        parts.append("rs:none")

    try:
        blob = read_agentic_state(case_id)
        n_user = sum(
            1
            for t in (blob.get("tasks") or [])
            if isinstance(t, dict) and str(t.get("source") or "").strip() == "user"
        )
        parts.append(f"user_tasks:{n_user}")
    except Exception:
        parts.append("user_tasks:?")

    return hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()


def try_run_agentic(
    case_id: str,
    *,
    reason: str,
    force: bool = False,
) -> Literal["ran", "skipped", "failed"]:
    """
    Gated call to run_agentic_reasoning. Respects reasoning_mode, fingerprint, interval, hourly cap.

    ``force`` (e.g. chat task): skip fingerprint match and per-case min-interval checks; still respects
    ``reasoning_mode == off`` unless we add a separate bypass — plan: off skips even force for token
    safety; user can set normal to enable.
    """
    try:
        cid = validate_case_id(case_id)
    except ValueError:
        _logger.warning("try_run_agentic: invalid case_id=%s", case_id)
        return "failed"

    ps = read_pipeline_state(cid)
    mode = str(ps.get("reasoning_mode") or "normal").strip().lower()
    if mode not in REASONING_MODES:
        mode = "normal"

    if mode == "off" and not force:
        _logger.info("try_run_agentic skipped case_id=%s reasoning_mode=off reason=%s", cid, reason)
        merge_pipeline_state(
            cid,
            {
                "reasoning_stale": True,
                "stale_reason": "reasoning_mode_off",
            },
        )
        return "skipped"

    if mode == "off" and force:
        _logger.info("try_run_agentic skipped case_id=%s reasoning_mode=off (force not honored when off)", cid)
        merge_pipeline_state(
            cid,
            {
                "reasoning_stale": True,
                "stale_reason": "reasoning_mode_off",
            },
        )
        return "skipped"

    fp = case_content_fingerprint(cid)
    last_fp = str(ps.get("last_content_fingerprint") or "").strip()
    last_at_raw = ps.get("last_agentic_run_at")
    run_ts = ps.get("agentic_run_timestamps")
    if not isinstance(run_ts, list):
        run_ts = []

    now = datetime.now(timezone.utc)

    if not force:
        if last_fp == fp and last_fp:
            _logger.info("try_run_agentic skipped case_id=%s unchanged fingerprint", cid)
            return "skipped"

        if last_at_raw:
            try:
                last_run = datetime.fromisoformat(str(last_at_raw).replace("Z", "+00:00"))
                delta = (now - last_run.astimezone(timezone.utc)).total_seconds()
                need = min_interval_seconds_for_mode(mode)
                if delta < need:
                    _logger.info(
                        "try_run_agentic skipped case_id=%s min_interval %.0fs < %.0fs",
                        cid,
                        delta,
                        need,
                    )
                    merge_pipeline_state(
                        cid,
                        {
                            "reasoning_stale": True,
                            "stale_reason": "min_interval",
                            "last_content_fingerprint_pending": fp,
                        },
                    )
                    return "skipped"
            except (ValueError, TypeError):
                pass

    hour_key = now.strftime("%Y%m%d%H")
    hour_bucket = str(ps.get("agentic_hour_bucket") or "")
    runs_in_hour = int(ps.get("agentic_runs_this_hour") or 0) if hour_bucket == hour_key else 0
    max_h = max_runs_per_hour_for_mode(mode)
    if not force and runs_in_hour >= max_h:
        _logger.info("try_run_agentic skipped case_id=%s hourly cap %d", cid, max_h)
        merge_pipeline_state(
            cid,
            {
                "reasoning_stale": True,
                "stale_reason": "hourly_cap",
            },
        )
        return "skipped"

    if not _global_slot_available():
        _logger.info("try_run_agentic skipped case_id=%s global per-minute cap", cid)
        merge_pipeline_state(
            cid,
            {
                "reasoning_stale": True,
                "stale_reason": "global_cap",
            },
        )
        return "skipped"

    snapshot = build_case_state_snapshot_for_agentic(cid)
    try:
        out = run_agentic_reasoning(cid, snapshot)
    except Exception:
        _logger.exception("try_run_agentic failed case_id=%s reason=%s", cid, reason)
        return "failed"

    if not out:
        _logger.warning("try_run_agentic empty result case_id=%s reason=%s", cid, reason)
        return "failed"

    _global_slot_commit()

    new_ts = list(run_ts)
    new_ts.append(now.isoformat())
    new_ts = new_ts[-50:]

    runs_in_hour = runs_in_hour + 1
    merge_pipeline_state(
        cid,
        {
            "last_agentic_run_at": now.isoformat(),
            "last_content_fingerprint": fp,
            "agentic_run_timestamps": new_ts,
            "agentic_hour_bucket": hour_key,
            "agentic_runs_this_hour": runs_in_hour,
            "reasoning_stale": False,
            "stale_reason": "",
        },
    )
    _logger.info("try_run_agentic ran case_id=%s reason=%s", cid, reason)
    try:
        from workflow.task_executor import maybe_enqueue_after_reasoning

        maybe_enqueue_after_reasoning(cid)
    except Exception:
        _logger.exception("maybe_enqueue_after_reasoning failed case_id=%s", cid)
    return "ran"


def enqueue_reasoning_job(
    case_id: str,
    reason: str,
    *,
    priority: int = 1,
    force: bool = False,
) -> None:
    """
    Queue a reasoning pass. Higher ``priority`` values are processed first.
    ``force`` relaxes fingerprint and min-interval (not hourly in v1 — chat uses force to skip those;
    hourly still applies unless we want chat to bypass — plan: force bypasses fingerprint + interval only).
    """
    try:
        validate_case_id(case_id)
    except ValueError:
        return
    # Lower tuple entry sorts first in PriorityQueue: use -priority so 2 runs before 1
    _job_queue.put((-priority, next(_seq), case_id, reason, force))


def _worker_loop() -> None:
    while True:
        try:
            neg_pri, _seqn, case_id, reason, force = _job_queue.get(timeout=1.0)
        except queue.Empty:
            continue
        try:
            try_run_agentic(case_id, reason=reason, force=force)
        except Exception:
            _logger.exception("reasoning worker error case_id=%s", case_id)
        finally:
            _job_queue.task_done()


def start_reasoning_worker() -> None:
    """Start daemon thread processing the reasoning queue (idempotent)."""
    global _worker_thread
    with _worker_start_lock:
        if _worker_thread is not None and _worker_thread.is_alive():
            return
        t = threading.Thread(target=_worker_loop, daemon=True, name="paradocs-reasoning-agent")
        t.start()
        _worker_thread = t
        _logger.info("Reasoning background worker started")
