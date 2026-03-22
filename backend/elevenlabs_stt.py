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


def transcribe_audio_for_ingest(path: Path) -> str:
    """
    Send a local audio (or video-with-audio) file to ElevenLabs STT.
    Returns plain transcript text, or empty string if the key is missing or the call fails.
    """
    key = _api_key()
    if not key:
        logger.warning("ELEVENLABS_API_KEY not set; skipping audio transcription for %s", path.name)
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

    model = _stt_model()
    tag_events = os.environ.get("ELEVENLABS_STT_TAG_EVENTS", "").lower() in ("1", "true", "yes")
    data: dict[str, str] = {
        "model_id": model,
        # Plainer transcript for embeddings unless ELEVENLABS_STT_TAG_EVENTS=true (adds (laughter), etc.)
        "tag_audio_events": "true" if tag_events else "false",
        "webhook": "false",
    }
    lang = os.environ.get("ELEVENLABS_STT_LANGUAGE", "").strip()
    if lang:
        data["language_code"] = lang

    files = {"file": (path.name, file_bytes, mime)}

    headers = {"xi-api-key": key}

    timeout = float(os.environ.get("ELEVENLABS_STT_TIMEOUT", "300").strip() or "300")

    try:
        with httpx.Client(timeout=timeout) as client:
            resp = client.post(_STT_URL, headers=headers, data=data, files=files)
    except httpx.RequestError as e:
        logger.warning("ElevenLabs STT request failed for %s: %s", path.name, e)
        return ""

    if resp.status_code != 200:
        detail = resp.text[:500] if resp.text else ""
        logger.warning(
            "ElevenLabs STT HTTP %s for %s: %s",
            resp.status_code,
            path.name,
            detail,
        )
        return ""

    try:
        body = resp.json()
    except Exception as e:
        logger.warning("ElevenLabs STT invalid JSON for %s: %s", path.name, e)
        return ""

    text = _extract_transcript_text(body)
    if not text:
        logger.warning("ElevenLabs STT returned no transcript text for %s", path.name)
    return text
