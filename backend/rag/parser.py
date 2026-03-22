from __future__ import annotations

import json

from fastapi import HTTPException

from groq_llm import generate_json

from schemas import Document, StructuredDocument

PARSER_SYSTEM_PROMPT = """You extract legal facts from source text.
Return STRICT JSON only. No markdown, no extra keys, no prose.

Rules:
- doc_id and case_id are provided in the user message. Echo them exactly in your JSON; do not invent or change them. Focus extraction on parties, events, claims, jurisdiction, damages, and summary from the source text only.
- Use ONLY the provided "Source text" block. Do not use outside knowledge, typical legal templates, or assumptions about what "usually" happens in a case.
- Extract only facts explicitly stated or clearly named in that text. If something is ambiguous or implied but not stated, omit it or use empty values with low confidence.
- Do NOT: predict outcomes, add legal conclusions, infer jurisdiction/court from party names alone, invent dates/amounts, or add parties not named in the text.
- Parties: include a person or entity only if their name (or clear identifier) appears in the source. Each party "role" MUST be exactly one of: plaintiff, defendant, other — never synonyms like "contracting", "party", or "counterparty". If plaintiff/defendant is not explicit in the text, use "other" and low confidence.
- Events / claims / damages: the "event", "type", and similar fields must be phrased from what the text actually says, not from general legal categories unless the text uses them.
- source_span MUST be an exact, contiguous copy-paste substring from the Source text (same spelling/punctuation). If you cannot find such a substring, set source_span to "" and set confidence to 0.2 or lower for that item (or omit the item if there is no support at all).
- summary.text: short neutral restatement of only what appears in the source. If the source is empty or non-informative, use "" with low summary.confidence.
- Dates and amounts: only if explicitly present; otherwise null or "".
- If unknown, use null for optional dates/amounts, empty strings, empty arrays, or low confidence.
- confidence values must be between 0 and 1; use lower values whenever support is weak or span is missing.

Required JSON shape:
{
  "doc_id": "string",
  "case_id": "string",
  "parties": [{"name":"string","role":"plaintiff|defendant|other","confidence":0.0}],
  "events": [{"event":"string","date":"string or null","confidence":0.0,"source_span":"string"}],
  "claims": [{"type":"string","confidence":0.0,"source_span":"string"}],
  "jurisdiction": {"value":"string","confidence":0.0},
  "damages":[{"type":"string","amount":"string or null","confidence":0.0,"source_span":"string"}],
  "summary": {"text":"string","confidence":0.0}
}
"""


def _normalize_parsed_dict(data: dict) -> dict:
    """Coerce legacy flat shapes toward StructuredDocument when possible."""
    if data.get("jurisdiction") is None:
        data["jurisdiction"] = {"value": "", "confidence": 0.0}
    if data.get("summary") is None:
        data["summary"] = {"text": "", "confidence": 0.0}
    if "jurisdiction" in data and isinstance(data["jurisdiction"], str):
        data["jurisdiction"] = {"value": data["jurisdiction"], "confidence": 0.0}
    if "summary" in data and isinstance(data["summary"], str):
        data["summary"] = {"text": data["summary"], "confidence": 0.0}
    for party in data.get("parties") or []:
        if not isinstance(party, dict):
            continue
        if "confidence" not in party:
            party["confidence"] = 0.0
        raw_role = party.get("role")
        if raw_role is not None:
            r = str(raw_role).strip().lower()
            if r not in ("plaintiff", "defendant", "other"):
                party["role"] = "other"
            else:
                party["role"] = r
    for ev in data.get("events") or []:
        if isinstance(ev, dict) and "source_span" not in ev:
            ev["source_span"] = ""
    for cl in data.get("claims") or []:
        if isinstance(cl, dict) and "source_span" not in cl:
            cl["source_span"] = ""
    for dm in data.get("damages") or []:
        if isinstance(dm, dict) and "source_span" not in dm:
            dm["source_span"] = ""
    if "jurisdiction" not in data or not isinstance(data["jurisdiction"], dict):
        data["jurisdiction"] = {"value": "", "confidence": 0.0}
    if "summary" not in data or not isinstance(data["summary"], dict):
        data["summary"] = {"text": "", "confidence": 0.0}
    return data


def _drop_ungrounded_spans(raw_text: str, data: dict) -> None:
    """If source_span is not a verbatim substring of raw_text, clear it and cap confidence."""
    for key in ("events", "claims", "damages"):
        for item in data.get(key) or []:
            if not isinstance(item, dict):
                continue
            span = (item.get("source_span") or "").strip()
            if not span:
                continue
            if span not in raw_text:
                item["source_span"] = ""
                try:
                    c = float(item.get("confidence", 1.0))
                except (TypeError, ValueError):
                    c = 1.0
                item["confidence"] = min(c, 0.2)


def parse_legal_structure(document: Document) -> StructuredDocument:
    user_prompt = (
        f"case_id={document.case_id}\n"
        f"doc_id={document.doc_id}\n"
        f"source={document.source}\n"
        f"timestamp={document.timestamp}\n\n"
        "Source text:\n"
        f"{document.raw_text}"
    )
    try:
        content = generate_json(PARSER_SYSTEM_PROMPT, user_prompt)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Groq parse failure: {exc}") from exc
    try:
        data = json.loads(content)
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=500, detail="Parser returned invalid JSON.") from exc

    data["case_id"] = document.case_id
    data["doc_id"] = document.doc_id
    data = _normalize_parsed_dict(data)
    _drop_ungrounded_spans(document.raw_text, data)
    try:
        return StructuredDocument.model_validate(data)
    except Exception as exc:
        raise HTTPException(status_code=422, detail=f"Structured validation failed: {exc}") from exc
