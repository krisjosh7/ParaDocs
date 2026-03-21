import os
import shutil
import subprocess
import tempfile
import atexit
from pathlib import Path
from typing import Any, Union
from uuid import uuid4

from fastapi import Body, FastAPI, File, HTTPException, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

app = FastAPI()
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


def cleanup_session_media() -> None:
    shutil.rmtree(SESSION_MEDIA_DIR, ignore_errors=True)


atexit.register(cleanup_session_media)


@app.on_event("shutdown")
def on_shutdown() -> None:
    cleanup_session_media()


@app.get("/health")
def health():
    return {"status": "ok"}


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
