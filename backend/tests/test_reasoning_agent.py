from __future__ import annotations

import json
from unittest.mock import patch

import pytest

from timeline_logic import empty_timeline_payload, write_timelines_json
from workflow.pipeline_state import merge_pipeline_state
from workflow.reasoning_agent import try_run_agentic

_FAKE_AGENTIC_JSON = json.dumps(
    {
        "hypotheses": [{"id": "h1", "theory": "T", "confidence": 0.5, "timeline_label": "primary", "supporting_event_refs": []}],
        "tasks": [{"id": "t1", "task": "Do thing", "reason": "gap", "source": "missing_info"}],
        "research_queries": ["q1"],
    },
)


def test_try_run_agentic_skips_repeat_when_fingerprint_unchanged(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("CASES_ROOT", str(tmp_path))
    monkeypatch.setenv("AGENTIC_MIN_INTERVAL_SECONDS", "0")
    monkeypatch.setenv("AGENTIC_GLOBAL_MAX_RUNS_PER_MINUTE", "0")

    cid = "case-ra-fp"
    (tmp_path / cid).mkdir(parents=True)
    (tmp_path / cid / "events.json").write_text("[]", encoding="utf-8")
    write_timelines_json(cid, empty_timeline_payload(cid))

    with patch("workflow.nodes.agentic_reasoning.generate_json", return_value=_FAKE_AGENTIC_JSON):
        assert try_run_agentic(cid, reason="test", force=False) == "ran"
        assert try_run_agentic(cid, reason="test", force=False) == "skipped"


@pytest.mark.parametrize("force", [False, True])
def test_try_run_agentic_respects_off_even_with_force(tmp_path, monkeypatch, force: bool) -> None:
    monkeypatch.setenv("CASES_ROOT", str(tmp_path))
    monkeypatch.setenv("AGENTIC_GLOBAL_MAX_RUNS_PER_MINUTE", "0")

    cid = "case-ra-off2"
    (tmp_path / cid).mkdir(parents=True)
    (tmp_path / cid / "events.json").write_text("[]", encoding="utf-8")
    write_timelines_json(cid, empty_timeline_payload(cid))
    merge_pipeline_state(cid, {"reasoning_mode": "off"})

    assert try_run_agentic(cid, reason="test", force=force) == "skipped"
