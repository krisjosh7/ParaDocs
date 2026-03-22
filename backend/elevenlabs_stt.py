"""ElevenLabs Speech-to-Text (Scribe) for transcribing uploaded audio into RAG raw text."""

from __future__ import annotations

import logging
import mimetypes
import os
from pathlib import Path
from typing import Any

import httpx

logger = logging.getLogger(__name__)

_STT_URL = "https://api.elevenlabs.io/v1/speech-to-text"


def _api_key() -> str:
    return os.environ.get("ELEVENLABS_API_KEY", "").strip()


def _stt_model() -> str:
    return (os.environ.get("ELEVENLABS_STT_MODEL", "scribe_v2").strip() or "scribe_v2")


def _stt_timeout() -> float:
    return float(os.environ.get("ELEVENLABS_STT_TIMEOUT", "300").strip() or "300")


def _extract_transcript_text(payload: dict[str, Any]) -> str:
    """Normalize ElevenLabs STT JSON to a single plain string."""
    if not isinstance(payload, dict):
        return ""
    # Synchronous chunk response
    text = payload.get("text")
    if isinstance(text, str) and text.strip():
        return text.strip()
    # Multichannel
    transcripts = payload.get("transcripts")
    if isinstance(transcripts, list):
        parts: list[str] = []
        for item in transcripts:
            if isinstance(item, dict):
                t = item.get("text")
                if isinstance(t, str) and t.strip():
                    parts.append(t.strip())
        if parts:
            return "\n\n".join(parts)
    # Webhook ack — no transcript inline
    if payload.get("message") and payload.get("request_id"):
        logger.warning("ElevenLabs STT returned webhook-style response without transcript text")
    return ""


def _elevenlabs_form_data() -> dict[str, str]:
    model = _stt_model()
    tag_events = os.environ.get("ELEVENLABS_STT_TAG_EVENTS", "").lower() in ("1", "true", "yes")
    data: dict[str, str] = {
        "model_id": model,
        "tag_audio_events": "true" if tag_events else "false",
        "webhook": "false",
    }
    lang = os.environ.get("ELEVENLABS_STT_LANGUAGE", "").strip()
    if lang:
        data["language_code"] = lang
    return data


def transcribe_bytes_sync(filename: str, file_bytes: bytes, mime: str) -> str:
    """Send raw audio bytes to ElevenLabs STT; returns transcript or empty string."""
    key = _api_key()
    if not key or not file_bytes:
        return ""

    files = {"file": (filename, file_bytes, mime)}
    headers = {"xi-api-key": key}
    data = _elevenlabs_form_data()
    timeout = _stt_timeout()

    try:
        with httpx.Client(timeout=timeout) as client:
            resp = client.post(_STT_URL, headers=headers, data=data, files=files)
    except httpx.RequestError as e:
        logger.warning("ElevenLabs STT request failed for %s: %s", filename, e)
        return ""

    if resp.status_code != 200:
        detail = resp.text[:500] if resp.text else ""
        logger.warning(
            "ElevenLabs STT HTTP %s for %s: %s",
            resp.status_code,
            filename,
            detail,
        )
        return ""

    try:
        body = resp.json()
    except Exception as e:
        logger.warning("ElevenLabs STT invalid JSON for %s: %s", filename, e)
        return ""

    text = _extract_transcript_text(body)
    if not text:
        logger.warning("ElevenLabs STT returned no transcript text for %s", filename)
    return text


async def transcribe_upload_bytes_async(filename: str, audio_bytes: bytes, mime: str) -> str:
    """Async variant for FastAPI (e.g. live session microphone chunks)."""
    key = _api_key()
    if not key or not audio_bytes:
        return ""

    files = {"file": (filename, audio_bytes, mime)}
    headers = {"xi-api-key": key}
    data = _elevenlabs_form_data()
    timeout = min(_stt_timeout(), 120.0)

    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await client.post(_STT_URL, headers=headers, data=data, files=files)
    except httpx.RequestError as e:
        logger.warning("ElevenLabs STT request failed for %s: %s", filename, e)
        return ""

    if resp.status_code != 200:
        detail = resp.text[:500] if resp.text else ""
        logger.warning(
            "ElevenLabs STT HTTP %s for %s: %s",
            resp.status_code,
            filename,
            detail,
        )
        return ""

    try:
        body = resp.json()
    except Exception as e:
        logger.warning("ElevenLabs STT invalid JSON for %s: %s", filename, e)
        return ""

    text = _extract_transcript_text(body)
    if not text:
        logger.warning("ElevenLabs STT returned no transcript text for %s", filename)
    return text


def transcribe_audio_for_ingest(path: Path) -> str:
    """
    Transcribe a local audio (or video-with-audio) file for RAG ingest.
    Tries ElevenLabs first, then Deepgram if the key is set and ElevenLabs
    yields no text or fails.
    """
    dg_env = os.environ.get("DEEPGRAM_API_KEY", "").strip()
    if not _api_key() and not dg_env:
        logger.warning(
            "Neither ELEVENLABS_API_KEY nor DEEPGRAM_API_KEY set; skipping audio transcription for %s",
            path.name,
        )
        return ""

    try:
        file_bytes = path.read_bytes()
    except OSError as e:
        logger.warning("Could not read audio file %s: %s", path, e)
        return ""

    if not file_bytes:
        return ""

    mime, _ = mimetypes.guess_type(path.name)
    if not mime:
        mime = "application/octet-stream"

    text = transcribe_bytes_sync(path.name, file_bytes, mime)
    if text.strip():
        return text

    from deepgram_stt import transcribe_bytes_sync as deepgram_transcribe_bytes

    dg_text = deepgram_transcribe_bytes(path.name, file_bytes, mime)
    if dg_text.strip():
        logger.info("STT fallback: Deepgram transcribed %s", path.name)
    return dg_text
