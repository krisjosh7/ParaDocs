"""Groq API helpers: retry on Groq 429 with backoff, then fall back to NVIDIA NIM (also retries 429)."""

from __future__ import annotations

import base64
import logging
import os
import re
import time
from pathlib import Path
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


def default_vision_model() -> str:
    return (
        os.environ.get("GROQ_VISION_MODEL", "meta-llama/llama-4-scout-17b-16e-instruct").strip()
        or "meta-llama/llama-4-scout-17b-16e-instruct"
    )


VISION_INGEST_SYSTEM = """You describe a single image for legal case evidence indexing (search and retrieval).

Strict rules:
- Report only what is directly observable: visible objects, scene/setting, readable text in the image, colors, layout, damage or markings if visible.
- Do not invent names, dates, document titles, dollar amounts, or legal conclusions that are not legible in the image.
- Do not identify real-world individuals by name unless that name appears in the image text.
- If something is blurry, cropped, occluded, or ambiguous, say so explicitly.
- If the user message includes an uploader caption, treat it as hints only: align your description with pixels; if the caption conflicts with the image, note that briefly and prioritize what you see.
- Prefer cautious phrasing when unsure ("appears to", "unclear whether", "partially visible").
- If the image is blank, nearly blank, or corrupted, say so in one or two short sentences.
- Output plain prose only (no markdown code fences). Short paragraphs are fine; avoid marketing tone.
"""


def describe_image_for_ingest(path: Path, *, caption: str = "") -> str:
    """
    Call Groq vision model to produce a factual image description for RAG.
    Returns empty string on failure (caller may still have title/caption in the header).
    """
    from rag.document_extract import prepare_image_for_vision_api

    prepared = prepare_image_for_vision_api(path)
    if prepared is None:
        return ""

    raw_bytes, mime = prepared
    data_url = f"data:{mime};base64,{base64.b64encode(raw_bytes).decode('ascii')}"

    user_text = "Describe this image for case documentation and retrieval, following your instructions."
    cap = (caption or "").strip()
    if cap:
        user_text += (
            "\n\nUploader-provided caption (may be incomplete or incorrect—verify against the image): "
            + cap
        )

    messages: list[dict[str, Any]] = [
        {"role": "system", "content": VISION_INGEST_SYSTEM},
        {
            "role": "user",
            "content": [
                {"type": "text", "text": user_text},
                {"type": "image_url", "image_url": {"url": data_url}},
            ],
        },
    ]

    try:
        client = _client()
    except RuntimeError as e:
        logger.warning("Vision description skipped: %s", e)
        return ""

    try:
        resp = client.chat.completions.create(
            model=default_vision_model(),
            messages=messages,
            temperature=0.2,
            max_completion_tokens=1536,
        )
    except RateLimitError as e:
        logger.warning("Groq rate limit on vision ingest: %s", e)
        return ""
    except Exception as e:
        logger.warning("Groq vision ingest failed: %s", e)
        return ""

    choice = resp.choices[0]
    content = choice.message.content
    if not content:
        return ""
    return _strip_thinking(content.strip())


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
    _max_retries: int = 6,
) -> str:
    """Call NVIDIA NIM API (Qwen 3.5 122B) as fallback, with retry on 429.

    Backoff schedule: 2s, 5s, 10s, 20s, 40s, 60s (capped at 60s).
    Total max wait across all retries is ~137s before giving up.
    """
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
        print(f"[NIM] Attempt {attempt + 1}/{_max_retries}...")
        resp = http_requests.post(
            _NVIDIA_BASE, json=payload, headers=headers, timeout=90,
        )
        if resp.status_code == 429:
            wait = min(2 * (2 ** attempt), 60)  # 2s, 4s, 8s, 16s, 32s, 60s
            logger.warning("NVIDIA NIM 429 (attempt %d/%d), retrying in %ds", attempt + 1, _max_retries, wait)
            print(f"[NIM] Rate limited (429). Waiting {wait}s before retry...")
            time.sleep(wait)
            continue
        resp.raise_for_status()
        data = resp.json()
        content = data["choices"][0]["message"]["content"]
        if not content:
            raise RuntimeError("NVIDIA NIM returned empty content")
        print(f"[NIM] Success on attempt {attempt + 1}")
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

    try:
        print(f"[LLM] Calling Groq ({kwargs['model']})...")
        resp = client.chat.completions.create(**kwargs)
        print(f"[LLM] Groq responded successfully")
    except RateLimitError:
        print(f"[LLM] Groq rate limited! Falling back to NVIDIA NIM ({_NVIDIA_MODEL})")
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


def chat_messages(messages: list[dict[str, str]], *, temperature: float = 0.3) -> str:
    """Multi-turn chat; first message should be system. Uses Groq with NVIDIA NIM fallback."""
    if not messages:
        raise ValueError("messages must not be empty")
    return _completion_text(messages, temperature=temperature, response_format=None)
