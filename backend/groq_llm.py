"""Groq API helpers with automatic fallback to NVIDIA NIM on rate limits."""

from __future__ import annotations

import logging
import os
import re
import time
from typing import Any

import requests as http_requests
from groq import Groq, RateLimitError

logger = logging.getLogger(__name__)

_THINK_RE = re.compile(r"<think>.*?</think>\s*", re.DOTALL)

# ── NVIDIA NIM fallback config ────────────────────────────────────────────────
_NVIDIA_BASE = "https://integrate.api.nvidia.com/v1/chat/completions"
_NVIDIA_MODEL = "qwen/qwen3.5-122b-a10b"


def default_model() -> str:
    return (
        os.environ.get("GROQ_MODEL", "llama-3.3-70b-versatile").strip() or "llama-3.3-70b-versatile"
    )


def _api_key() -> str:
    return os.environ.get("GROQ_API_KEY", "").strip()


def _nvidia_api_key() -> str:
    return os.environ.get("NVIDIA_API_KEY", "").strip()


def _client() -> Groq:
    key = _api_key()
    if not key:
        raise RuntimeError("GROQ_API_KEY is not set (add it to backend/.env or the environment)")
    return Groq(api_key=key)


def _strip_thinking(text: str) -> str:
    """Remove <think>...</think> blocks that thinking-mode models emit."""
    return _THINK_RE.sub("", text).strip()


def _nvidia_completion(
    messages: list[dict[str, str]],
    *,
    temperature: float,
    response_format: dict[str, str] | None,
    _max_retries: int = 3,
) -> str:
    """Call NVIDIA NIM API (Qwen 3.5 122B) as fallback, with retry on 429."""
    key = _nvidia_api_key()
    if not key:
        raise RuntimeError("NVIDIA_API_KEY is not set — cannot fall back to NVIDIA NIM")

    payload: dict[str, Any] = {
        "model": _NVIDIA_MODEL,
        "messages": messages,
        "temperature": temperature,
        "max_tokens": 4096,
        "stream": False,
        "chat_template_kwargs": {"enable_thinking": False},
    }
    if response_format is not None:
        payload["response_format"] = response_format

    headers = {
        "accept": "application/json",
        "content-type": "application/json",
        "authorization": f"Bearer {key}",
    }

    for attempt in range(_max_retries):
        resp = http_requests.post(
            _NVIDIA_BASE, json=payload, headers=headers, timeout=60,
        )
        if resp.status_code == 429:
            wait = 2 ** attempt  # 1s, 2s, 4s
            logger.warning("NVIDIA NIM 429 (attempt %d/%d), retrying in %ds", attempt + 1, _max_retries, wait)
            time.sleep(wait)
            continue
        resp.raise_for_status()
        data = resp.json()
        content = data["choices"][0]["message"]["content"]
        if not content:
            raise RuntimeError("NVIDIA NIM returned empty content")
        return _strip_thinking(content.strip())

    raise RuntimeError(f"NVIDIA NIM rate-limited after {_max_retries} retries")


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

    try:
        resp = client.chat.completions.create(**kwargs)
    except RateLimitError:
        logger.warning("Groq rate limit on %s, falling back to NVIDIA NIM (%s)", kwargs["model"], _NVIDIA_MODEL)
        return _nvidia_completion(messages, temperature=temperature, response_format=response_format)

    choice = resp.choices[0]
    content = choice.message.content
    if not content:
        raise RuntimeError("Groq returned empty content")
    return _strip_thinking(content)


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
