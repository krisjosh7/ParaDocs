"""
Fill missing Event.date values using dates present in the source text.

The legal-structure LLM is conservative about dates; this layer applies
document-level filing/decided lines and local calendar phrases near each
source_span without inventing facts not in the text.
"""

from __future__ import annotations

import re
from datetime import date

# ISO in typical ingest headers (CourtListener, etc.)
_HEADER_ISO_RE = re.compile(
    r"(?:Date\s+Filed|Date\s+Decided)\s*:\s*(\d{4}-\d{2}-\d{2})\b",
    re.IGNORECASE,
)

_MONTH = (
    r"(?:January|February|March|April|May|June|July|August|September|October|November|December)"
)
_LONG_DATE_RE = re.compile(rf"\b{_MONTH}\s+\d{{1,2}},\s*\d{{4}}\b")

# Narrative milestones that align with a docket filing / opinion date when the body omits one.
_LITIGATION_DATE_HINTS = re.compile(
    r"\b("
    r"sued|lawsuit|complaint|counterclaimed|counterclaim|"
    r"filed\s+(?:a\s+)?(?:suit|complaint|action|appeal)|"
    r"(?:plaintiff|defendant)\s+filed"
    r")\b",
    re.IGNORECASE,
)

# Do not attach a filing header date to contract-formation style events.
_CONTRACT_FORMATION_HINTS = re.compile(
    r"\b("
    r"contracted|contract\s+was\s+executed|executed\s+(?:the\s+)?agreement|"
    r"entered\s+into\s+(?:a\s+)?contract|signed\s+(?:the\s+)?agreement"
    r")\b",
    re.IGNORECASE,
)


def _iso_to_long_calendar(iso: str) -> str:
    y, m, d = map(int, iso.split("-"))
    dt = date(y, m, d)
    month_name = dt.strftime("%B")
    return f"{month_name} {dt.day}, {dt.year}"


def _header_filing_iso(raw_text: str) -> str | None:
    """First Date Filed / Date Decided ISO value near the top of the document."""
    if not raw_text:
        return None
    head = raw_text[:4000]
    m = _HEADER_ISO_RE.search(head)
    return m.group(1) if m else None


def _event_blob(ev: dict) -> str:
    return f"{ev.get('event') or ''} {ev.get('source_span') or ''}"


def _nearest_long_date_around_span(raw_text: str, span: str, *, radius: int = 520) -> str | None:
    span = (span or "").strip()
    if len(span) < 2:
        return None
    idx = raw_text.find(span)
    if idx < 0:
        return None
    center = idx + len(span) // 2
    lo = max(0, center - radius)
    hi = min(len(raw_text), center + radius)
    window = raw_text[lo:hi]
    anchor = center - lo
    best: str | None = None
    best_dist = 10**9
    for m in _LONG_DATE_RE.finditer(window):
        mid = (m.start() + m.end()) // 2
        dist = abs(mid - anchor)
        if dist < best_dist:
            best_dist = dist
            best = m.group(0)
    return best


def enrich_events_from_source_text(events: list[dict], raw_text: str) -> None:
    """
    Mutate events in place: set date when missing and a supporting phrase exists in raw_text.
    Safe to call on parser output before StructuredDocument validation.
    """
    if not events or not raw_text:
        return

    filing_iso = _header_filing_iso(raw_text)

    for ev in events:
        if not isinstance(ev, dict):
            continue
        cur = ev.get("date")
        if cur is not None and str(cur).strip():
            continue

        blob = _event_blob(ev)

        if filing_iso and _LITIGATION_DATE_HINTS.search(blob):
            if not _CONTRACT_FORMATION_HINTS.search(blob):
                ev["date"] = _iso_to_long_calendar(filing_iso)
                continue

        span = (ev.get("source_span") or "").strip()
        nearby = _nearest_long_date_around_span(raw_text, span)
        if nearby:
            ev["date"] = nearby
