from __future__ import annotations

from event_date_enrichment import enrich_events_from_source_text


def test_filing_header_applied_to_suit_not_contract() -> None:
    raw = """Idrive Logistics LLC v. Integracore LLC (2018 UT App 40)
Date Filed: 2018-03-15

¶1 iDrive Logistics LLC contracted with IntegraCore LLC to provide services.
iDrive sued IntegraCore for breach and IntegraCore counterclaimed.
"""
    events = [
        {
            "event": "contracted to provide services",
            "date": None,
            "confidence": 0.8,
            "source_span": "iDrive Logistics LLC contracted with IntegraCore LLC to provide services",
        },
        {
            "event": "iDrive sued IntegraCore",
            "date": None,
            "confidence": 0.9,
            "source_span": "iDrive sued IntegraCore for breach",
        },
        {
            "event": "IntegraCore counterclaimed",
            "date": None,
            "confidence": 0.9,
            "source_span": "IntegraCore counterclaimed",
        },
    ]
    enrich_events_from_source_text(events, raw)
    assert events[0]["date"] is None
    assert events[1]["date"] == "March 15, 2018"
    assert events[2]["date"] == "March 15, 2018"


def test_long_form_date_near_short_span() -> None:
    raw = """Caption: Themes for NF-2044, Dock B incident

OBJECTIVES
- Lock in a clear narrative of the February 6, 2025 delivery (NF-2044), condition of Dock B.
"""
    events = [
        {
            "event": "Dock B incident",
            "date": None,
            "confidence": 0.8,
            "source_span": "Dock B incident",
        },
    ]
    enrich_events_from_source_text(events, raw)
    assert events[0]["date"] == "February 6, 2025"


def test_skips_when_date_already_set() -> None:
    raw = "Date Filed: 2018-03-15\n\nParty sued defendant."
    events = [
        {
            "event": "Party sued defendant",
            "date": "January 1, 2000",
            "confidence": 0.9,
            "source_span": "Party sued defendant",
        },
    ]
    enrich_events_from_source_text(events, raw)
    assert events[0]["date"] == "January 1, 2000"
