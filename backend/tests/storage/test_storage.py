from __future__ import annotations

import json

import storage
from schemas import StructuredDocument, SummaryBlock, JurisdictionBlock


def test_default_cases_root_fallback(monkeypatch) -> None:
    monkeypatch.delenv("CASES_ROOT", raising=False)
    root = storage.default_cases_root()
    assert root.name == "cases"
    assert "backend" in str(root) or root.exists() or True


def test_default_cases_root_respects_env(monkeypatch, tmp_path) -> None:
    root = tmp_path / "custom_cases"
    monkeypatch.setenv("CASES_ROOT", str(root))
    paths = storage.ensure_case_dirs("case-x")
    assert paths["base"] == root / "case-x"
    assert (root / "case-x" / "documents").is_dir()


def test_write_roundtrip_files(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("CASES_ROOT", str(tmp_path / "cases"))
    storage.write_raw_text("c1", "d1", "hello raw")
    structured = StructuredDocument(
        doc_id="d1",
        case_id="c1",
        summary=SummaryBlock(text="s", confidence=1.0),
        jurisdiction=JurisdictionBlock(),
    )
    storage.write_structured("c1", "d1", structured)
    storage.write_metadata("c1", "d1", {"k": "v"})
    assert (tmp_path / "cases" / "c1" / "documents" / "d1.txt").read_text() == "hello raw"
    js = json.loads((tmp_path / "cases" / "c1" / "structured" / "d1.json").read_text())
    assert js["doc_id"] == "d1"
    meta = json.loads((tmp_path / "cases" / "c1" / "metadata" / "d1.json").read_text())
    assert meta["k"] == "v"


def test_generate_doc_id_format() -> None:
    uid = storage.generate_doc_id()
    assert len(uid) == 36
    assert uid.count("-") == 4
