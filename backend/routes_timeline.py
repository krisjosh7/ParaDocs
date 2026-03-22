from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException

from context_catalog import validate_case_id
from timeline_logic import empty_timeline_payload, read_timelines_json

router = APIRouter(prefix="/cases/{case_id}", tags=["timeline"])


@router.get("/timeline")
def get_case_timeline(case_id: str) -> dict[str, Any]:
    try:
        validate_case_id(case_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    data = read_timelines_json(case_id)
    if data is None:
        return empty_timeline_payload(case_id)
    return data
