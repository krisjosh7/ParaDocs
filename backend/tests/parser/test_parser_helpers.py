from __future__ import annotations

import pytest

from parser import _drop_ungrounded_spans, _normalize_parsed_dict


def test_normalize_flat_jurisdiction_and_summary() -> None:
    data = {
        "doc_id": "d1",
        "case_id": "c1",
        "jurisdiction": "VA",
        "summary": "Short summary.",
        "parties": [{"name": "A", "role": "other"}],
        "events": [],
        "claims": [],
        "damages": [],
    }
    out = _normalize_parsed_dict(data)
    assert out["jurisdiction"] == {"value": "VA", "confidence": 0.0}
    assert out["summary"] == {"text": "Short summary.", "confidence": 0.0}
    assert out["parties"][0]["confidence"] == 0.0


def test_normalize_replaces_non_dict_jurisdiction_and_summary() -> None:
    data = {
        "doc_id": "d1",
        "case_id": "c1",
        "parties": [],
        "events": [],
        "claims": [],
        "damages": [],
        "jurisdiction": [],
        "summary": [],
    }
    out = _normalize_parsed_dict(data)
    assert out["jurisdiction"] == {"value": "", "confidence": 0.0}
    assert out["summary"] == {"text": "", "confidence": 0.0}


def test_normalize_jurisdiction_summary_missing_keys() -> None:
    data = {
        "doc_id": "d1",
        "case_id": "c1",
        "parties": [],
        "events": [],
        "claims": [],
        "damages": [],
    }
    out = _normalize_parsed_dict(data)
    assert out["jurisdiction"] == {"value": "", "confidence": 0.0}
    assert out["summary"] == {"text": "", "confidence": 0.0}


def test_normalize_adds_source_span_keys() -> None:
    data = {
        "doc_id": "d1",
        "case_id": "c1",
        "jurisdiction": {"value": "", "confidence": 0.0},
        "summary": {"text": "", "confidence": 0.0},
        "parties": [],
        "events": [{"event": "x", "date": None, "confidence": 0.5}],
        "claims": [{"type": "t", "confidence": 0.5}],
        "damages": [{"type": "d", "amount": None, "confidence": 0.5}],
    }
    out = _normalize_parsed_dict(data)
    assert out["events"][0]["source_span"] == ""
    assert out["claims"][0]["source_span"] == ""
    assert out["damages"][0]["source_span"] == ""


def test_drop_ungrounded_spans_clears_fake_span() -> None:
    raw = "The contract was breached on Monday."
    data = {
        "events": [
            {
                "event": "breach",
                "date": None,
                "confidence": 0.99,
                "source_span": "this text is not in raw",
            }
        ],
        "claims": [],
        "damages": [],
    }
    _drop_ungrounded_spans(raw, data)
    assert data["events"][0]["source_span"] == ""
    assert data["events"][0]["confidence"] == pytest.approx(0.2)


def test_drop_ungrounded_skips_non_dict_items() -> None:
    raw = "hello"
    data = {"events": ["not-a-dict"], "claims": [], "damages": []}
    _drop_ungrounded_spans(raw, data)
    assert data["events"] == ["not-a-dict"]


def test_drop_ungrounded_skips_empty_span() -> None:
    raw = "hello"
    data = {
        "events": [{"event": "e", "source_span": "  ", "confidence": 0.9}],
        "claims": [],
        "damages": [],
    }
    _drop_ungrounded_spans(raw, data)
    assert data["events"][0]["source_span"] == "  "


def test_drop_ungrounded_spans_bad_confidence_type() -> None:
    raw = "hello"
    data = {
        "events": [{"event": "e", "source_span": "not in raw", "confidence": "broken"}],
        "claims": [],
        "damages": [],
    }
    _drop_ungrounded_spans(raw, data)
    assert data["events"][0]["confidence"] == 0.2


def test_drop_ungrounded_spans_keeps_verbatim_span() -> None:
    raw = "The contract was breached on Monday."
    data = {
        "events": [
            {
                "event": "breach",
                "date": None,
                "confidence": 0.9,
                "source_span": "breached",
            }
        ],
        "claims": [],
        "damages": [],
    }
    _drop_ungrounded_spans(raw, data)
    assert data["events"][0]["source_span"] == "breached"
    assert data["events"][0]["confidence"] == pytest.approx(0.9)
