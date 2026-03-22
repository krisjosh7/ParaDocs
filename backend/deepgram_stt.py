"""Deepgram speech-to-text — optional fallback when ElevenLabs STT fails or is unset."""

from __future__ import annotations

import logging
import mimetypes
import os
from pathlib import Path
from typing import Any

import httpx

logger = logging.getLogger(__name__)

_LISTEN_URL = "https://api.deepgram.com/v1/listen"


def _api_key() -> str:
    return os.environ.get("DEEPGRAM_API_KEY", "").strip()


def _model() -> str:
    return (os.environ.get("DEEPGRAM_STT_MODEL", "nova-2").strip() or "nova-2")


def _timeout() -> float:
    return float(os.environ.get("DEEPGRAM_STT_TIMEOUT", "300").strip() or "300")


def _extract_transcript_text(payload: dict[str, Any]) -> str:
    try:
        channels = payload.get("results", {}).get("channels")
        if not isinstance(channels, list) or not channels:
            return ""
        alts = channels[0].get("alternatives")
        if not isinstance(alts, list) or not alts:
            return ""
        t = alts[0].get("transcript")
        return t.strip() if isinstance(t, str) else ""
    except (AttributeError, IndexError, TypeError):
        return ""


def transcribe_file(path: Path) -> str:
    """
    Transcribe a local file via Deepgram pre-recorded API.
    Returns plain text or empty string on failure / missing key.
    """
    key = _api_key()
    if not key:
        return ""

    try:
        file_bytes = path.read_bytes()
    except OSError as e:
        logger.warning("Could not read audio file for Deepgram %s: %s", path, e)
        return ""

    if not file_bytes:
        return ""

    mime, _ = mimetypes.guess_type(path.name)
    if not mime:
        mime = "application/octet-stream"

    return transcribe_bytes_sync(path.name, file_bytes, mime)


def transcribe_bytes_sync(filename: str, file_bytes: bytes, mime: str) -> str:
    key = _api_key()
    if not key or not file_bytes:
        return ""

    params: dict[str, str] = {"model": _model()}
    lang = os.environ.get("DEEPGRAM_STT_LANGUAGE", "").strip()
    if lang:
        params["language"] = lang

    headers = {
        "Authorization": f"Token {key}",
        "Content-Type": mime,
    }

    try:
        with httpx.Client(timeout=_timeout()) as client:
            resp = client.post(_LISTEN_URL, params=params, headers=headers, content=file_bytes)
    except httpx.RequestError as e:
        logger.warning("Deepgram STT request failed for %s: %s", filename, e)
        return ""

    if resp.status_code != 200:
        detail = resp.text[:500] if resp.text else ""
        logger.warning("Deepgram STT HTTP %s for %s: %s", resp.status_code, filename, detail)
        return ""

    try:
        body = resp.json()
    except Exception as e:
        logger.warning("Deepgram STT invalid JSON for %s: %s", filename, e)
        return ""

    text = _extract_transcript_text(body)
    if not text:
        logger.warning("Deepgram STT returned no transcript text for %s", filename)
    return text


async def transcribe_upload_bytes_async(filename: str, audio_bytes: bytes, mime: str) -> str:
    """Async variant for FastAPI upload handlers (e.g. /session/transcribe)."""
    key = _api_key()
    if not key or not audio_bytes:
        return ""

    params: dict[str, str] = {"model": _model()}
    lang = os.environ.get("DEEPGRAM_STT_LANGUAGE", "").strip()
    if lang:
        params["language"] = lang

    headers = {
        "Authorization": f"Token {key}",
        "Content-Type": mime,
    }

    timeout = min(_timeout(), 120.0)

    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await client.post(_LISTEN_URL, params=params, headers=headers, content=audio_bytes)
    except httpx.RequestError as e:
        logger.warning("Deepgram STT request failed for %s: %s", filename, e)
        return ""

    if resp.status_code != 200:
        detail = resp.text[:500] if resp.text else ""
        logger.warning("Deepgram STT HTTP %s for %s: %s", resp.status_code, filename, detail)
        return ""

    try:
        body = resp.json()
    except Exception as e:
        logger.warning("Deepgram STT invalid JSON for %s: %s", filename, e)
        return ""

    text = _extract_transcript_text(body)
    if not text:
        logger.warning("Deepgram STT returned no transcript text for %s", filename)
    return text
