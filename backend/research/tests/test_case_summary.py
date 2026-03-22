from __future__ import annotations

from pathlib import Path

import pytest

from research.case_summary import public_summary, read_raw, record_research_run


def test_record_and_public_summary(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CASES_ROOT", str(tmp_path))
    cid = "case-sum-1"

    record_research_run(
        cid,
        [{"id": "c1", "case_name": "A"}, {"id": "c2", "case_name": "B"}],
        "no_new_results",
        1,
    )
    record_research_run(
        cid,
        [{"id": "c2", "case_name": "B"}, {"id": "c3", "case_name": "C"}],
        "max_iter",
        2,
    )

    pub = public_summary(cid)
    assert pub["unique_sources_count"] == 3
    assert pub["total_runs"] == 2
    assert pub["last_run_added_unique"] == 1
    assert pub["last_batch_stored_count"] == 2
    assert pub["last_stop_reason"] == "max_iter"
    assert pub["last_iteration"] == 2


def test_get_summary_endpoint(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """GET /research/cases/{id}/summary on isolated app (avoids importing full main / Chroma stack)."""
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from research.router import router as research_router

    monkeypatch.setenv("CASES_ROOT", str(tmp_path))
    cid = "case-api-sum"
    record_research_run(cid, [{"id": "x1"}], None, 1)

    app = FastAPI()
    app.include_router(research_router)
    c = TestClient(app)
    r = c.get(f"/research/cases/{cid}/summary")
    assert r.status_code == 200
    body = r.json()
    assert body["unique_sources_count"] == 1
    assert body["total_runs"] == 1
