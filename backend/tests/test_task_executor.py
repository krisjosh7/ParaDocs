from __future__ import annotations

from unittest.mock import patch

from workflow.agentic_state_store import read_agentic_state, write_agentic_state
from workflow.pipeline_state import merge_pipeline_state
from workflow.state import initial_case_state
from workflow.task_executor import execute_tasks_light, maybe_enqueue_after_reasoning


def test_execute_tasks_light_updates_task_with_summary(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("CASES_ROOT", str(tmp_path))
    monkeypatch.setenv("TASK_EXEC_MIN_INTERVAL_SECONDS", "0")
    monkeypatch.setenv("TASK_EXEC_GLOBAL_MAX_PER_MINUTE", "0")

    cid = "case-te-1"
    (tmp_path / cid).mkdir(parents=True)
    write_agentic_state(
        cid,
        {
            "hypotheses": [],
            "tasks": [
                {
                    "id": "t1",
                    "task": "Find lease terms",
                    "reason": "gap",
                    "source": "missing_info",
                    "status": "pending",
                }
            ],
            "research_queries": [],
        },
    )

    fake_hits = [
        {
            "document": "Monthly rent is $500.",
            "metadata": {"doc_id": "doc-a"},
            "id": "chunk-1",
        }
    ]

    with (
        patch("workflow.task_executor.query_case", return_value=fake_hits),
        patch(
            "workflow.task_executor.generate_text",
            return_value="- Rent is $500 per month (doc-a).",
        ),
    ):
        out = execute_tasks_light(cid, task_id="t1", force_bypass_cooldown=True)

    assert out.get("ran") == 1
    blob = read_agentic_state(cid)
    t0 = blob["tasks"][0]
    assert t0.get("status") in ("done", "complete")
    assert "500" in (t0.get("execution_summary") or "")


def test_execute_tasks_light_no_hits_no_llm(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("CASES_ROOT", str(tmp_path))
    monkeypatch.setenv("TASK_EXEC_MIN_INTERVAL_SECONDS", "0")
    monkeypatch.setenv("TASK_EXEC_GLOBAL_MAX_PER_MINUTE", "0")

    cid = "case-te-2"
    (tmp_path / cid).mkdir(parents=True)
    write_agentic_state(
        cid,
        {
            "hypotheses": [],
            "tasks": [{"id": "t1", "task": "X", "reason": "", "source": "agent", "status": "pending"}],
            "research_queries": [],
        },
    )

    with (
        patch("workflow.task_executor.query_case", return_value=[]),
        patch("workflow.task_executor.generate_text") as mock_gen,
    ):
        out = execute_tasks_light(cid, task_id="t1", force_bypass_cooldown=True)

    mock_gen.assert_not_called()
    assert out.get("ran") == 1
    assert "No indexed" in (read_agentic_state(cid)["tasks"][0].get("execution_summary") or "")


def test_execute_tasks_light_skips_user_execution_type(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("CASES_ROOT", str(tmp_path))

    cid = "case-te-3"
    (tmp_path / cid).mkdir(parents=True)
    write_agentic_state(
        cid,
        {
            "hypotheses": [],
            "tasks": [
                {
                    "id": "u1",
                    "task": "Build spreadsheet",
                    "source": "user",
                    "type": "execution",
                    "status": "pending",
                }
            ],
            "research_queries": [],
        },
    )

    out = execute_tasks_light(cid, task_id=None, max_tasks=1, force_bypass_cooldown=True)
    assert out.get("skipped") == "no_eligible_task"


def test_maybe_enqueue_after_reasoning_respects_mode(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("CASES_ROOT", str(tmp_path))

    cid = "case-te-4"
    (tmp_path / cid).mkdir(parents=True)

    with patch("workflow.task_executor.enqueue_task_execution_job") as mock_q:
        maybe_enqueue_after_reasoning(cid)
        mock_q.assert_not_called()

    merge_pipeline_state(cid, {"task_execution_mode": "auto_light"})
    with patch("workflow.task_executor.enqueue_task_execution_job") as mock_q:
        maybe_enqueue_after_reasoning(cid)
        mock_q.assert_called_once()


def test_merge_tasks_preserves_execution_summary(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("CASES_ROOT", str(tmp_path))
    from workflow.nodes.agentic_reasoning import run_agentic_reasoning

    cid = "case-te-merge"
    (tmp_path / cid).mkdir(parents=True)
    write_agentic_state(
        cid,
        {
            "hypotheses": [],
            "tasks": [
                {
                    "id": "a1",
                    "task": "Old label",
                    "source": "missing_info",
                    "status": "done",
                    "execution_summary": "Kept result",
                    "executed_at": "2025-01-01T00:00:00Z",
                }
            ],
            "research_queries": [],
        },
    )

    fake = '{"hypotheses": [], "tasks": [{"id": "a1", "task": "New label", "reason": "r", "source": "missing_info", "status": "pending"}], "research_queries": []}'
    with patch("workflow.nodes.agentic_reasoning.generate_json", return_value=fake):
        run_agentic_reasoning(cid, initial_case_state(cid, ""))

    blob = read_agentic_state(cid)
    t0 = blob["tasks"][0]
    assert t0.get("execution_summary") == "Kept result"
    assert t0.get("executed_at") == "2025-01-01T00:00:00Z"
