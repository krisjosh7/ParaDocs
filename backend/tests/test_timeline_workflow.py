from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from main import app
from timeline_logic import build_timeline_payload, read_case_events, rebuild_case_timeline, token_jaccard
from workflow.timeline_graph import run_timeline_workflow


@pytest.fixture(autouse=True)
def disable_timeline_branch_llm(monkeypatch: pytest.MonkeyPatch) -> None:
    """Avoid real Groq calls during timeline tests."""
    monkeypatch.setenv("PARADOCS_TIMELINE_BRANCH_LLM", "0")


@pytest.fixture
def case_root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setenv("CASES_ROOT", str(tmp_path))
    cid = "case-z"
    base = tmp_path / cid
    base.mkdir(parents=True)
    return base


def test_token_jaccard_disjoint() -> None:
    assert token_jaccard("apple orange", "banana kiwi") == 0.0


def test_build_timeline_orders_by_sort_date_then_index(case_root: Path) -> None:
    cid = case_root.name
    events = [
        {"date": "2024-06-02", "event": "Second day", "source_span": "b", "doc_id": "d1", "confidence": 0.8},
        {"date": "2024-06-01", "event": "First day", "source_span": "a", "doc_id": "d1", "confidence": 0.8},
    ]
    (case_root / "events.json").write_text(json.dumps(events), encoding="utf-8")

    payload = build_timeline_payload(cid, read_case_events(cid))
    entries = payload["primary"]["entries"]
    assert [e["sort_date"] for e in entries] == ["2024-06-01", "2024-06-02"]
    assert payload["conflicts"] == []


def test_same_day_conflict_picks_higher_support(case_root: Path) -> None:
    cid = case_root.name
    # Same calendar day, very different wording -> conflict group; 0.9 confidence beats 0.4
    events = [
        {
            "date": "2024-03-01",
            "event": "Plaintiff filed motion to dismiss",
            "source_span": "short",
            "doc_id": "doc-a",
            "confidence": 0.4,
        },
        {
            "date": "March 1, 2024",
            "event": "Defendant acquired subsidiary assets",
            "source_span": "longer span text here",
            "doc_id": "doc-b",
            "confidence": 0.9,
        },
    ]
    assert token_jaccard(events[0]["event"], events[1]["event"]) < 0.35

    (case_root / "events.json").write_text(json.dumps(events), encoding="utf-8")
    payload = build_timeline_payload(cid, read_case_events(cid))

    assert len(payload["primary"]["entries"]) == 1
    winner = payload["primary"]["entries"][0]
    assert "Defendant acquired" in winner["title"]
    assert len(payload["conflicts"]) == 1
    assert winner.get("conflict_id")
    assert len(winner.get("alternates") or []) == 1
    assert "Plaintiff filed" in (winner["alternates"][0].get("title") or "")
    assert winner.get("branch_llm", {}).get("skipped") is True
    assert winner["alternates"][0].get("source_context")


def test_empty_events_json(case_root: Path) -> None:
    cid = case_root.name
    (case_root / "events.json").write_text("[]", encoding="utf-8")
    payload = rebuild_case_timeline(cid)
    assert payload["primary"]["entries"] == []
    timelines_path = case_root / "timelines.json"
    assert timelines_path.is_file()
    on_disk = json.loads(timelines_path.read_text(encoding="utf-8"))
    assert on_disk["primary"]["entries"] == []


def test_run_timeline_workflow_persists(case_root: Path) -> None:
    cid = case_root.name
    events = [
        {"date": "2025-01-01", "event": "Start", "source_span": "s", "doc_id": "d", "confidence": 1.0},
    ]
    (case_root / "events.json").write_text(json.dumps(events), encoding="utf-8")

    final = run_timeline_workflow(cid)
    assert final["timelines_payload"]["primary"]["entries"]
    assert (case_root / "timelines.json").is_file()


def test_get_timeline_api_empty_when_missing_file(case_root: Path) -> None:
    cid = case_root.name
    client = TestClient(app)
    r = client.get(f"/cases/{cid}/timeline")
    assert r.status_code == 200
    body = r.json()
    assert body["case_id"] == cid
    assert body["primary"]["entries"] == []
