from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel, Field

from workflow import initial_case_state, run_case_workflow

router = APIRouter(prefix="/cases", tags=["case-workflow"])


class RunCaseWorkflowBody(BaseModel):
    raw_text: str
    source: str = Field(default="upload", description='One of: "upload" | "tts" | "web"')


@router.post("/{case_id}/workflow/run")
async def post_run_case_workflow(case_id: str, body: RunCaseWorkflowBody) -> dict:
    """Run ingest → events → timeline → optional one-time research → reasoning for one document."""
    state = initial_case_state(case_id, body.raw_text, body.source)
    final = await run_case_workflow(state)
    return dict(final)
