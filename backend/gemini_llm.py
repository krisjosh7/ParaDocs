"""Shared Google Gemini API helpers (used by RAG parser and research prompts)."""

from __future__ import annotations

import os
from typing import Any

import google.generativeai as genai


def default_model() -> str:
    return os.environ.get("GEMINI_MODEL", "gemini-2.0-flash").strip() or "gemini-2.0-flash"


def _api_key() -> str:
    return os.environ.get("GEMINI_API_KEY", "").strip()


def require_api_key() -> None:
    if not _api_key():
        raise RuntimeError("GEMINI_API_KEY is not set (add it to backend/.env or the environment)")


def _configure() -> None:
    require_api_key()
    genai.configure(api_key=_api_key())


def _response_text(response: Any) -> str:
    try:
        return response.text
    except ValueError as exc:
        reason = "unknown"
        if getattr(response, "candidates", None):
            c0 = response.candidates[0]
            reason = str(getattr(c0, "finish_reason", "unknown"))
        raise RuntimeError(f"Gemini returned no text (finish_reason={reason})") from exc


def generate_json(system_instruction: str, user_text: str) -> str:
    """Structured JSON output (matches prior Ollama `format=json` behavior)."""
    _configure()
    model = genai.GenerativeModel(
        model_name=default_model(),
        system_instruction=system_instruction,
    )
    response = model.generate_content(
        user_text,
        generation_config=genai.GenerationConfig(
            temperature=0,
            response_mime_type="application/json",
        ),
    )
    return _response_text(response)


def generate_text(system_instruction: str, user_text: str, *, temperature: float = 0.3) -> str:
    """Plain-text completion (research queries / scoring)."""
    _configure()
    model = genai.GenerativeModel(
        model_name=default_model(),
        system_instruction=system_instruction,
    )
    response = model.generate_content(
        user_text,
        generation_config=genai.GenerationConfig(temperature=temperature),
    )
    return _response_text(response)
