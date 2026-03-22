import os
import shutil
import subprocess
import tempfile
import atexit
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, Literal, Union
from uuid import uuid4

from dotenv import load_dotenv

_backend_dir = Path(__file__).resolve().parent
load_dotenv(_backend_dir / ".env")
load_dotenv(_backend_dir.parent / ".env")

from fastapi import Body, FastAPI, File, HTTPException, Request, UploadFile
from pydantic import BaseModel, Field
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from context_catalog import validate_case_id
from routes_chat import router as chat_router
from routes_contexts import router as contexts_router
from routes_discovered import router as discovered_router
from routes_timeline import router as timeline_router
from routes_case_workflow import router as case_workflow_router
from rag.router import router as rag_router
from rag.vector_store import delete_chunks_for_case_id
from storage import create_case_record, default_cases_root, delete_case_tree, list_case_summaries
from workflow.agentic_state_store import read_agentic_state
from workflow.pipeline_state import merge_pipeline_state, read_pipeline_state

# Routers — each subgraph registers its own router here
from research.router import router as research_router
from session.router import router as session_router


@asynccontextmanager
async def _app_lifespan(_: FastAPI):
    from workflow.reasoning_agent import start_reasoning_worker
    from workflow.task_executor import start_task_execution_worker

    start_reasoning_worker()
    start_task_execution_worker()
    yield
    cleanup_session_media()


app = FastAPI(lifespan=_app_lifespan)
SESSION_MEDIA_DIR = Path(tempfile.mkdtemp(prefix="paradocs-media-"))
LEGACY_MEDIA_DIR = Path(__file__).resolve().parent / "media"
# Remove old persisted media folder from earlier implementation if present.
shutil.rmtree(LEGACY_MEDIA_DIR, ignore_errors=True)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.mount("/media", StaticFiles(directory=SESSION_MEDIA_DIR), name="media")
app.include_router(rag_router)
app.include_router(chat_router)
app.include_router(contexts_router)
app.include_router(discovered_router)
app.include_router(timeline_router)
app.include_router(case_workflow_router)


def cleanup_session_media() -> None:
    shutil.rmtree(SESSION_MEDIA_DIR, ignore_errors=True)


atexit.register(cleanup_session_media)


app.include_router(research_router)
app.include_router(session_router)


class CaseSummaryOut(BaseModel):
    id: str
    title: str
    summary: str


class CaseCreateIn(BaseModel):
    title: str = Field(..., min_length=1, max_length=500)
    summary: str = Field(default="", max_length=50000)


class AgenticStateOut(BaseModel):
    """Persisted agent reasoning output (tasks, hypotheses, suggested queries)."""

    version: int
    case_id: str
    hypotheses: list[Any]
    tasks: list[Any]
    research_queries: list[Any]
    reasoning_mode: str = Field(default="normal", description="off | normal | aggressive")
    reasoning_stale: bool = Field(default=False, description="True when a refresh is pending or blocked by caps")
    stale_reason: str | None = Field(default=None, description="Machine-readable stale reason from pipeline_state")
    last_agentic_run_at: str | None = Field(default=None, description="ISO timestamp of last successful agentic LLM run")
    task_execution_mode: str = Field(
        default="manual",
        description="manual (suggest only + on-demand run) | auto_light (run one light task after each reasoning refresh)",
    )
    last_task_execution_at: str | None = Field(default=None, description="ISO timestamp of last light task execution")


class AgentSettingsIn(BaseModel):
    reasoning_mode: Literal["off", "normal", "aggressive"] | None = Field(
        default=None,
        description="Background agentic LLM: off (no runs), normal, or aggressive (higher caps).",
    )
    task_execution_mode: Literal["manual", "auto_light"] | None = Field(
        default=None,
        description="Light task execution: manual vs auto after reasoning.",
    )


class TaskExecuteIn(BaseModel):
    task_id: str | None = Field(default=None, description="Run this task id; if omitted, runs the next eligible task")
    max_tasks: int = Field(default=1, ge=1, le=5)
    force_rerun: bool = Field(default=False, description="If true, allow re-running tasks already marked done")


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/cases", response_model=list[CaseSummaryOut])
def list_cases():
    return list_case_summaries()


@app.post("/cases")
def create_case(body: CaseCreateIn) -> dict[str, str | dict[str, str]]:
    title = body.title.strip()
    if not title:
        raise HTTPException(status_code=400, detail="title is required")
    try:
        case = create_case_record(title, body.summary)
    except OSError as e:
        raise HTTPException(status_code=500, detail="Could not create case directory") from e
    return {"status": "created", "case": case}


@app.post("/cases/{case_id}/agent/settings")
def post_case_agent_settings(case_id: str, body: AgentSettingsIn) -> dict[str, str]:
    try:
        cid = validate_case_id(case_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    if not (default_cases_root() / cid).is_dir():
        raise HTTPException(status_code=404, detail="Case not found")
    updates: dict[str, Any] = {}
    if body.reasoning_mode is not None:
        updates["reasoning_mode"] = body.reasoning_mode
    if body.task_execution_mode is not None:
        updates["task_execution_mode"] = body.task_execution_mode
    if not updates:
        raise HTTPException(status_code=400, detail="No settings provided")
    merge_pipeline_state(cid, updates)
    ps = read_pipeline_state(cid)
    return {
        "case_id": cid,
        "reasoning_mode": str(ps.get("reasoning_mode") or "normal"),
        "task_execution_mode": str(ps.get("task_execution_mode") or "manual"),
    }


@app.get("/cases/{case_id}/agentic", response_model=AgenticStateOut)
def get_case_agentic_state(case_id: str) -> AgenticStateOut:
    """Agent-generated tasks and reasoning artifacts for the case dashboard."""
    try:
        cid = validate_case_id(case_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    if not (default_cases_root() / cid).is_dir():
        raise HTTPException(status_code=404, detail="Case not found")
    raw = read_agentic_state(cid)
    ps = read_pipeline_state(cid)
    sr = str(ps.get("stale_reason") or "").strip() or None
    lra = ps.get("last_agentic_run_at")
    last_at = str(lra).strip() if lra else None
    lte = ps.get("last_task_execution_at")
    last_exec = str(lte).strip() if lte else None
    return AgenticStateOut(
        version=int(raw.get("version") or 1),
        case_id=str(raw.get("case_id") or cid),
        hypotheses=list(raw.get("hypotheses") or []),
        tasks=list(raw.get("tasks") or []),
        research_queries=list(raw.get("research_queries") or []),
        reasoning_mode=str(ps.get("reasoning_mode") or "normal").strip() or "normal",
        reasoning_stale=bool(ps.get("reasoning_stale")),
        stale_reason=sr,
        last_agentic_run_at=last_at,
        task_execution_mode=str(ps.get("task_execution_mode") or "manual").strip() or "manual",
        last_task_execution_at=last_exec,
    )


@app.post("/cases/{case_id}/agent/tasks/execute")
def post_case_task_execute(case_id: str, body: TaskExecuteIn) -> dict[str, Any]:
    """Run light RAG+LLM execution for one or more tasks (token-capped)."""
    try:
        cid = validate_case_id(case_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    if not (default_cases_root() / cid).is_dir():
        raise HTTPException(status_code=404, detail="Case not found")
    from workflow.task_executor import execute_tasks_light

    try:
        tid = (body.task_id or "").strip() or None
        out = execute_tasks_light(
            cid,
            task_id=tid,
            max_tasks=body.max_tasks,
            force_bypass_cooldown=True,
            force_rerun=body.force_rerun,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    return {"case_id": cid, **out}


@app.delete("/cases/{case_id}")
def delete_case(case_id: str) -> dict[str, str]:
    try:
        cid = validate_case_id(case_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    if not (default_cases_root() / cid).is_dir():
        raise HTTPException(status_code=404, detail="Case not found")
    delete_chunks_for_case_id(cid)
    delete_case_tree(cid)
    return {"status": "deleted", "case_id": cid}


@app.post("/echo")
def echo(body: Union[dict, list] = Body(...)) -> Any:
    return body


@app.post("/upload/video")
async def upload_video(request: Request, file: UploadFile = File(...)) -> dict[str, str]:
    if not file.filename:
        raise HTTPException(status_code=400, detail="Missing video filename.")

    in_suffix = Path(file.filename).suffix or ".bin"
    input_path = SESSION_MEDIA_DIR / f"tmp-{uuid4()}{in_suffix}"
    output_name = f"video-{uuid4()}.mp4"
    output_path = SESSION_MEDIA_DIR / output_name

    ffmpeg_bin = os.environ.get("FFMPEG_BIN", "ffmpeg")
    if ffmpeg_bin == "ffmpeg":
        try:
            from imageio_ffmpeg import get_ffmpeg_exe  # type: ignore

            ffmpeg_bin = get_ffmpeg_exe()
        except Exception:
            # Fall back to PATH lookup if imageio-ffmpeg is unavailable.
            ffmpeg_bin = "ffmpeg"
    ffmpeg_cmd = [
        ffmpeg_bin,
        "-y",
        "-i",
        str(input_path),
        "-map",
        "0:v:0",
        "-map",
        "0:a:0?",
        "-vf",
        "scale='if(gt(iw,ih),640,-2)':'if(gt(iw,ih),-2,640)':flags=lanczos,setsar=1,format=yuv420p,fps=30",
        "-sn",
        "-dn",
        "-map_metadata",
        "-1",
        "-map_chapters",
        "-1",
        "-c:v",
        "libx264",
        "-preset",
        "veryfast",
        "-crf",
        "23",
        "-pix_fmt",
        "yuv420p",
        "-profile:v",
        "baseline",
        "-level:v",
        "3.1",
        "-x264-params",
        "bframes=0:keyint=60:min-keyint=60:scenecut=0:ref=1:cabac=0",
        "-movflags",
        "+faststart",
        "-c:a",
        "aac",
        "-b:a",
        "128k",
        "-ar",
        "48000",
        "-ac",
        "2",
        str(output_path),
    ]

    try:
        with input_path.open("wb") as f:
            shutil.copyfileobj(file.file, f)
    finally:
        await file.close()

    try:
        proc = subprocess.run(ffmpeg_cmd, capture_output=True, text=True, check=False)
    except FileNotFoundError as exc:
        if output_path.exists():
            output_path.unlink(missing_ok=True)
        raise HTTPException(
            status_code=500,
            detail="FFmpeg is not installed on the server. Install it or set FFMPEG_BIN.",
        ) from exc
    finally:
        input_path.unlink(missing_ok=True)

    if proc.returncode != 0:
        output_path.unlink(missing_ok=True)
        err_tail = (proc.stderr or "").strip().splitlines()[-8:]
        raise HTTPException(
            status_code=400,
            detail="Video encoding failed.\n" + "\n".join(err_tail),
        )

    return {
        "url": str(request.base_url).rstrip("/") + f"/media/{output_name}",
        "file_name": output_name,
    }
