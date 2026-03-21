from __future__ import annotations

from io import BytesIO
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from main import app


def test_upload_video_missing_filename() -> None:
    """Multipart may yield 422 (validation) or 400 (app) depending on client; both reject."""
    client = TestClient(app)
    r = client.post(
        "/upload/video",
        files={"file": ("", BytesIO(b"x"), "video/mp4")},
    )
    assert r.status_code in (400, 422)


@patch("imageio_ffmpeg.get_ffmpeg_exe", side_effect=RuntimeError("no bundled ffmpeg"))
@patch("main.subprocess.run")
def test_upload_video_imageio_fallback_uses_path_ffmpeg(mock_run, _mock_gfe) -> None:
    """Covers main.py except branch when imageio_ffmpeg lookup fails."""
    mock_run.return_value = MagicMock(returncode=0, stderr="")
    client = TestClient(app)
    r = client.post(
        "/upload/video",
        files={"file": ("clip.mp4", BytesIO(b"x"), "video/mp4")},
    )
    assert r.status_code == 200


@patch("main.subprocess.run")
def test_upload_video_success(mock_run) -> None:
    mock_run.return_value = MagicMock(returncode=0, stderr="")
    client = TestClient(app)
    r = client.post(
        "/upload/video",
        files={"file": ("clip.mp4", BytesIO(b"not-really-video"), "video/mp4")},
    )
    assert r.status_code == 200
    data = r.json()
    assert "url" in data and "file_name" in data
    assert data["file_name"].endswith(".mp4")


@patch("main.subprocess.run")
def test_upload_video_ffmpeg_not_found(mock_run) -> None:
    mock_run.side_effect = FileNotFoundError()
    client = TestClient(app)
    r = client.post(
        "/upload/video",
        files={"file": ("clip.mp4", BytesIO(b"x"), "video/mp4")},
    )
    assert r.status_code == 500
    assert "FFmpeg" in r.json()["detail"]


@patch("main.subprocess.run")
def test_upload_video_encode_failed(mock_run) -> None:
    mock_run.return_value = MagicMock(returncode=1, stderr="error line\nfail")
    client = TestClient(app)
    r = client.post(
        "/upload/video",
        files={"file": ("clip.mp4", BytesIO(b"x"), "video/mp4")},
    )
    assert r.status_code == 400
    assert "Video encoding failed" in r.json()["detail"]
