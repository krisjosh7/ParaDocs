"""Groq API helpers: retry on Groq 429 with backoff, then fall back to NVIDIA NIM (also retries 429)."""

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


def _groq_rate_limit_extra_attempts() -> int:
    """How many *additional* tries after the first 429 before falling back to NIM (clamped)."""
    raw = os.environ.get("GROQ_RATE_LIMIT_RETRIES", "3").strip()
    try:
        n = int(raw)
    except ValueError:
        n = 3
    return max(0, min(n, 12))


def _groq_rate_limit_backoff_base_seconds() -> float:
    raw = os.environ.get("GROQ_RATE_LIMIT_RETRY_BASE_SECONDS", "1.5").strip()
    try:
        s = float(raw)
    except ValueError:
        s = 1.5
    return max(0.25, min(s, 120.0))


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
    _max_retries: int = 4,
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
            wait = min(60.0, float(2**attempt))
            logger.warning(
                "NVIDIA NIM 429 (attempt %d/%d), retrying in %.0fs",
                attempt + 1,
                _max_retries,
                wait,
            )
            time.sleep(wait)
            continue
        resp.raise_for_status()
        data = resp.json()
        content = data["choices"][0]["message"]["content"]
        if not content:
            raise RuntimeError("NVIDIA NIM returned empty content")
        return _strip_thinking(content.strip())

    raise RuntimeError(f"NVIDIA NIM rate-limited after {_max_retries} attempts")


def _groq_daily_token_limit_hit(exc: BaseException) -> bool:
    """Groq TPD (tokens-per-day) exhaustion won't clear with short backoff; skip retry loop."""
    s = str(exc).lower()
    if "tokens per day" in s:
        return True
    return "tpd" in s and ("limit" in s or "exceeded" in s)


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

    extra = _groq_rate_limit_extra_attempts()
    base_wait = _groq_rate_limit_backoff_base_seconds()
    total_attempts = extra + 1

    for attempt in range(total_attempts):
        try:
            resp = client.chat.completions.create(**kwargs)
        except RateLimitError as e:
            if _groq_daily_token_limit_hit(e):
                logger.warning(
                    "Groq daily token limit hit on %s — skipping Groq retries; using NVIDIA NIM (%s)",
                    kwargs["model"],
                    _NVIDIA_MODEL,
                )
                return _nvidia_completion(
                    messages, temperature=temperature, response_format=response_format
                )
            if attempt >= extra:
                logger.warning(
                    "Groq rate limited on %s after %d attempt(s); falling back to NVIDIA NIM (%s)",
                    kwargs["model"],
                    total_attempts,
                    _NVIDIA_MODEL,
                )
                return _nvidia_completion(
                    messages, temperature=temperature, response_format=response_format
                )
            wait = min(90.0, base_wait * (2**attempt))
            logger.warning(
                "Groq rate limited on %s (attempt %d/%d), retrying in %.1fs",
                kwargs["model"],
                attempt + 1,
                total_attempts,
                wait,
            )
            time.sleep(wait)
            continue

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
