from __future__ import annotations

import json
from unittest.mock import patch

import pytest
from fastapi import HTTPException

from rag.parser import parse_legal_structure
from schemas import Document


def _minimal_llm_json() -> str:
    return json.dumps(
        {
            "doc_id": "ignored",
            "case_id": "ignored",
            "parties": [],
            "events": [],
            "claims": [],
            "jurisdiction": {"value": "", "confidence": 0.0},
            "damages": [],
            "summary": {"text": "One sentence.", "confidence": 0.8},
        }
    )


@patch("rag.parser.generate_json")
def test_parse_legal_structure_success(mock_gen) -> None:
    mock_gen.return_value = _minimal_llm_json()
    doc = Document(
        case_id="case-p",
        doc_id="doc-p",
        raw_text="The parties settled.",
        source="upload",
        timestamp="2024-01-01T00:00:00+00:00",
    )
    out = parse_legal_structure(doc)
    assert out.case_id == "case-p"
    assert out.doc_id == "doc-p"
    assert out.summary.text == "One sentence."


@patch("rag.parser.generate_json")
def test_parse_legal_structure_invalid_json(mock_gen) -> None:
    mock_gen.return_value = "not json {"
    doc = Document(
        case_id="c",
        doc_id="d",
        raw_text="x",
        source="upload",
        timestamp="2024-01-01T00:00:00+00:00",
    )
    with pytest.raises(HTTPException) as ei:
        parse_legal_structure(doc)
    assert ei.value.status_code == 500


@patch("rag.parser.generate_json")
def test_parse_legal_structure_gemini_failure(mock_gen) -> None:
    mock_gen.side_effect = RuntimeError("connection refused")
    doc = Document(
        case_id="c",
        doc_id="d",
        raw_text="x",
        source="upload",
        timestamp="2024-01-01T00:00:00+00:00",
    )
    with pytest.raises(HTTPException) as ei:
        parse_legal_structure(doc)
    assert ei.value.status_code == 500
    assert "Gemini" in str(ei.value.detail)


@patch("rag.parser.generate_json")
def test_parse_legal_structure_validation_failure(mock_gen) -> None:
    bad = json.dumps(
        {
            "doc_id": "d",
            "case_id": "c",
            "parties": "not_a_list",
            "events": [],
            "claims": [],
            "jurisdiction": {"value": "", "confidence": 0.0},
            "damages": [],
            "summary": {"text": "", "confidence": 0.0},
        }
    )
    mock_gen.return_value = bad
    doc = Document(
        case_id="c",
        doc_id="d",
        raw_text="x",
        source="upload",
        timestamp="2024-01-01T00:00:00+00:00",
    )
    with pytest.raises(HTTPException) as ei:
        parse_legal_structure(doc)
    assert ei.value.status_code == 422
