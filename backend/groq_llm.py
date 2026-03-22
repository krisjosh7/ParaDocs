"""Groq API helpers (OpenAI-compatible chat completions for Llama / Mixtral on Groq)."""

from __future__ import annotations

import os
from typing import Any

from groq import Groq


def default_model() -> str:
    return (
        os.environ.get("GROQ_MODEL", "llama-3.3-70b-versatile").strip() or "llama-3.3-70b-versatile"
    )


def _api_key() -> str:
    return os.environ.get("GROQ_API_KEY", "").strip()


def _client() -> Groq:
    key = _api_key()
    if not key:
        raise RuntimeError("GROQ_API_KEY is not set (add it to backend/.env or the environment)")
    return Groq(api_key=key)


def _completion_text(
    messages: list[dict[str, str]],
    *,
    temperature: float,
    response_format: dict[str, str] | None,
) -> str:
    client = _client()
    kwargs: dict[str, Any] = {
        "model": default_model(),
        "messages": messages,
        "temperature": temperature,
    }
    if response_format is not None:
        kwargs["response_format"] = response_format
    resp = client.chat.completions.create(**kwargs)
    choice = resp.choices[0]
    content = choice.message.content
    if not content:
        raise RuntimeError("Groq returned empty content")
    return content.strip()


def generate_json(system_instruction: str, user_text: str) -> str:
    """Structured JSON output (matches prior Ollama `format=json` behavior)."""
    return _completion_text(
        [
            {"role": "system", "content": system_instruction},
            {"role": "user", "content": user_text},
        ],
        temperature=0,
        response_format={"type": "json_object"},
    )


def generate_text(system_instruction: str, user_text: str, *, temperature: float = 0.3) -> str:
    """Plain-text completion (research queries / scoring)."""
    return _completion_text(
        [
            {"role": "system", "content": system_instruction},
            {"role": "user", "content": user_text},
        ],
        temperature=temperature,
        response_format=None,
    )
