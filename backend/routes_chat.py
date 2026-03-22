from __future__ import annotations

import logging
from typing import Any, Literal
from uuid import uuid4

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from context_catalog import validate_case_id
from groq_llm import chat_messages
from rag.vector_store import query_case
from workflow.agentic_state_store import read_agentic_state, write_agentic_state
from workflow.nodes.agentic_reasoning import classify_user_message_as_task
from workflow.reasoning_agent import enqueue_reasoning_job

logger = logging.getLogger(__name__)

router = APIRouter(tags=["chat"])

TOP_K = 8
CONTEXT_MAX_CHARS = 10_000
MAX_HISTORY_MESSAGES = 20

CHAT_SYSTEM_PREFIX = (
    "You are a legal assistant helping with case-related questions. "
    "Answer only using the CONTEXT block below when it is non-empty. "
    "If the answer is not supported by the context, say you do not have enough information "
    "in the provided documents. Do not invent facts. Be concise and professional.\n\n"
)


class ChatMessageIn(BaseModel):
    role: Literal["user", "assistant"]
    content: str = Field(..., min_length=0, max_length=32000)


class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=8000)
    case_id: str | None = Field(default=None, max_length=256)
    chat_history: list[ChatMessageIn] = Field(default_factory=list)


class ChatResponse(BaseModel):
    response: str
    sources: list[str]
    task_detected: bool = False
    reasoning: dict[str, Any] | None = None
    reasoning_refresh_queued: bool = False


def _build_context_block(hits: list[dict]) -> tuple[str, list[str]]:
    """Format retrieval hits; cap total characters. Returns (text, unique doc_ids)."""
    parts: list[str] = []
    doc_ids: list[str] = []
    seen: set[str] = set()
    total = 0
    for i, hit in enumerate(hits, start=1):
        md = hit.get("metadata") or {}
        doc_id = str(md.get("doc_id", "")).strip()
        chunk_type = str(md.get("type", "")).strip()
        text = str(hit.get("document", "")).strip()
        if not text:
            continue
        header = f"[{i}]"
        if doc_id:
            header += f" doc_id={doc_id}"
        if chunk_type:
            header += f" type={chunk_type}"
        block = f"{header}\n{text}\n"
        if total + len(block) > CONTEXT_MAX_CHARS:
            break
        parts.append(block)
        total += len(block)
        if doc_id and doc_id not in seen:
            seen.add(doc_id)
            doc_ids.append(doc_id)
    return "\n".join(parts).strip(), sorted(doc_ids)


@router.post("/chat", response_model=ChatResponse)
def chat_endpoint(body: ChatRequest) -> ChatResponse:
    msg = body.message.strip()
    if not msg:
        raise HTTPException(status_code=422, detail="message is required")

    hits: list[dict] = []
    sources: list[str] = []
    cid: str | None = None
    if body.case_id and body.case_id.strip():
        try:
            cid = validate_case_id(body.case_id.strip())
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e)) from e
        try:
            hits = query_case(cid, msg, top_k=TOP_K, type_filter=None)
        except Exception as e:
            logger.exception("query_case failed for chat")
            raise HTTPException(status_code=502, detail="Retrieval failed") from e
        context_text, sources = _build_context_block(hits)
    else:
        context_text = ""

    context_section = (
        f"CONTEXT:\n{context_text}\n"
        if context_text
        else "CONTEXT:\n(No case documents were retrieved. The user did not select a case or the case has no indexed content.)\n"
    )

    if cid is not None:
        try:
            is_task, task_meta = classify_user_message_as_task(msg)
        except Exception:
            logger.exception("chat task classification failed; falling back to normal chat")
            is_task, task_meta = False, None
        if is_task and task_meta:
            try:
                blob = read_agentic_state(cid)
                typ = str(task_meta.get("type") or "investigation").strip()
                if typ not in ("execution", "research", "investigation"):
                    typ = "investigation"
                priority = str(task_meta.get("priority") or "medium").strip() or "medium"
                status = str(task_meta.get("status") or "pending").strip() or "pending"
                user_task: dict[str, Any] = {
                    "id": str(uuid4()),
                    "task": str(task_meta.get("task") or msg).strip() or msg,
                    "type": typ,
                    "priority": priority,
                    "status": status,
                    "source": "user",
                    "reason": "User-assigned task via chat",
                }
                blob["tasks"].append(user_task)
                write_agentic_state(cid, blob)
                # Token control: full agentic LLM runs in background (high priority + force).
                enqueue_reasoning_job(cid, "chat_task", priority=2, force=True)
                final = read_agentic_state(cid)
                reasoning = {
                    "hypotheses": final.get("hypotheses") or [],
                    "tasks": final.get("tasks") or [],
                    "research_queries": final.get("research_queries") or [],
                }
            except Exception:
                logger.exception("chat agentic reasoning path failed; falling back to normal chat")
                is_task = False

            if is_task and task_meta:
                ack_prefix = (
                    "You are a legal assistant. The user assigned a new task to the case agent; "
                    "the task was saved and a background reasoning refresh was queued (hypotheses / tasks / "
                    "research suggestions may update within a short time). "
                    "Reply in one or two short sentences: confirm the task was recorded and that reasoning "
                    "will update shortly. Do not paste large JSON.\n\n"
                    f"Current snapshot: {len(reasoning['hypotheses'])} hypotheses, {len(reasoning['tasks'])} tasks, "
                    f"{len(reasoning['research_queries'])} research queries.\n\n"
                )
                system_content = ack_prefix + context_section
                history = body.chat_history[-MAX_HISTORY_MESSAGES:]
                groq_messages: list[dict[str, str]] = [{"role": "system", "content": system_content}]
                for m in history:
                    c = (m.content or "").strip()
                    if not c:
                        continue
                    groq_messages.append({"role": m.role, "content": c})
                groq_messages.append({"role": "user", "content": msg})
                try:
                    reply = chat_messages(groq_messages, temperature=0.3)
                except RuntimeError as e:
                    logger.warning("chat LLM error: %s", e)
                    raise HTTPException(status_code=503, detail=str(e)) from e
                except Exception as e:
                    logger.exception("chat LLM failed")
                    raise HTTPException(status_code=502, detail="Language model request failed") from e
                return ChatResponse(
                    response=reply,
                    sources=sources,
                    task_detected=True,
                    reasoning=reasoning,
                    reasoning_refresh_queued=True,
                )

    system_content = CHAT_SYSTEM_PREFIX + context_section

    history = body.chat_history[-MAX_HISTORY_MESSAGES:]
    groq_messages = [{"role": "system", "content": system_content}]
    for m in history:
        c = (m.content or "").strip()
        if not c:
            continue
        groq_messages.append({"role": m.role, "content": c})
    groq_messages.append({"role": "user", "content": msg})

    try:
        reply = chat_messages(groq_messages, temperature=0.3)
    except RuntimeError as e:
        logger.warning("chat LLM error: %s", e)
        raise HTTPException(status_code=503, detail=str(e)) from e
    except Exception as e:
        logger.exception("chat LLM failed")
        raise HTTPException(status_code=502, detail="Language model request failed") from e

    return ChatResponse(
        response=reply,
        sources=sources,
        task_detected=False,
        reasoning=None,
        reasoning_refresh_queued=False,
    )
