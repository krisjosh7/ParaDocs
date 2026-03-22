from __future__ import annotations

from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from schemas import Document, Party, StoreDocumentRequest, StructuredDocument


def test_document_timestamp_string_passthrough() -> None:
    d = Document(
        case_id="c",
        doc_id="d",
        raw_text="x",
        source="upload",
        timestamp="2024-01-01T00:00:00+00:00",
    )
    assert d.timestamp == "2024-01-01T00:00:00+00:00"


def test_document_timestamp_coerces_datetime() -> None:
    d = Document(
        case_id="c",
        doc_id="d",
        raw_text="x",
        source="upload",
        timestamp=datetime(2024, 1, 1, 12, 0, 0, tzinfo=timezone.utc),
    )
    assert d.timestamp.startswith("2024-01-01")


def test_store_document_request_timestamp_string_unchanged() -> None:
    r = StoreDocumentRequest(
        case_id="c",
        raw_text="t",
        source="upload",
        timestamp="2024-02-02T00:00:00+00:00",
    )
    assert r.timestamp == "2024-02-02T00:00:00+00:00"


def test_store_document_request_timestamp_none() -> None:
    r = StoreDocumentRequest(case_id="c", raw_text="t", source="upload", timestamp=None)
    assert r.timestamp is None


def test_store_document_request_timestamp_coercion() -> None:
    r = StoreDocumentRequest(
        case_id="c",
        raw_text="t",
        source="upload",
        timestamp=datetime(2024, 6, 1, 0, 0, 0),
    )
    assert "2024-06-01" in r.timestamp


def test_document_invalid_source() -> None:
    with pytest.raises(ValidationError):
        Document(
            case_id="c",
            doc_id="d",
            raw_text="x",
            source="invalid",  # type: ignore[arg-type]
            timestamp="2024-01-01T00:00:00+00:00",
        )


def test_party_role_contracting_coerced_to_other() -> None:
    p = Party(name="Acme", role="contracting", confidence=0.9)  # type: ignore[arg-type]
    assert p.role == "other"


def test_structured_document_accepts_nonstandard_party_roles() -> None:
    doc = StructuredDocument.model_validate(
        {
            "doc_id": "d1",
            "case_id": "c1",
            "parties": [{"name": "X", "role": "contracting party", "confidence": 0.5}],
            "events": [],
            "claims": [],
            "jurisdiction": {"value": "", "confidence": 0.0},
            "damages": [],
            "summary": {"text": "", "confidence": 0.0},
        }
    )
    assert doc.parties[0].role == "other"
