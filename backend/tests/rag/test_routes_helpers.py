from __future__ import annotations

from datetime import datetime, timezone

from routes_rag import (
    _claim_chunk_text,
    _dedupe_claims,
    _dedupe_events,
    _event_chunk_text,
    _timestamp_iso,
)
from schemas import Claim, Event, StructuredDocument, SummaryBlock, JurisdictionBlock


def test_timestamp_iso_none_uses_utc_string() -> None:
    s = _timestamp_iso(None)
    assert "T" in s or "-" in s


def test_timestamp_iso_datetime_naive_gets_utc() -> None:
    s = _timestamp_iso(datetime(2024, 1, 1, 12, 0, 0))
    assert "2024-01-01" in s
    assert "+00:00" in s


def test_timestamp_iso_string_passthrough() -> None:
    assert _timestamp_iso("2024-05-05T00:00:00Z") == "2024-05-05T00:00:00Z"


def test_timestamp_iso_aware_datetime() -> None:
    dt = datetime(2024, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
    assert _timestamp_iso(dt).startswith("2024-01-01")


def test_event_and_claim_chunk_text() -> None:
    e = Event(event="filing", date=None, confidence=0.5, source_span="  span  ")
    assert "filing" in _event_chunk_text(e)
    assert "span" in _event_chunk_text(e)
    c = Claim(type="tort", confidence=0.5, source_span="")
    assert _claim_chunk_text(c) == "tort"


def test_dedupe_events_and_claims() -> None:
    s = StructuredDocument(
        doc_id="d",
        case_id="c",
        summary=SummaryBlock(),
        jurisdiction=JurisdictionBlock(),
        events=[
            Event(event="Same", date=None, confidence=1.0, source_span="a"),
            Event(event="same", date=None, confidence=1.0, source_span="a"),
            Event(event="", date=None, confidence=1.0, source_span=""),
        ],
        claims=[
            Claim(type="X", confidence=1.0, source_span="s"),
            Claim(type="x", confidence=1.0, source_span="s"),
            Claim(type=" ", confidence=1.0, source_span=""),
        ],
    )
    assert len(_dedupe_events(s)) == 1
    assert len(_dedupe_claims(s)) == 1
