from __future__ import annotations

import mimetypes
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from fastapi import APIRouter, BackgroundTasks, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel

from context_catalog import (
    filter_items_by_query,
    format_added_label,
    make_text_preview,
    new_context_id,
    read_catalog,
    validate_case_id,
    write_catalog,
    context_library_paths,
)
from storage import delete_stored_document_files
from rag.context_rag import background_ingest_context_to_rag

router = APIRouter(prefix="/cases/{case_id}/contexts", tags=["contexts"])

ALLOWED_TYPES = frozenset({"text", "image", "video", "audio", "document", "research"})


class ContextItemOut(BaseModel):
    id: str
    type: str
    title: str
    caption: str = ""
    addedLabel: str
    fileName: str | None = None
    textPreview: str | None = None
    textFull: str | None = None
    imageSrc: str | None = None
    videoSrc: str | None = None
    audioSrc: str | None = None
    documentSrc: str | None = None
    docSubtype: str | None = None
    uploadedFile: bool | None = None
    sourceUrl: str | None = None


class ContextListOut(BaseModel):
    items: list[ContextItemOut]


def _catalog_to_response_item(
    request: Request,
    case_id: str,
    row: dict[str, Any],
) -> ContextItemOut:
    cid = str(row.get("id", ""))
    ctype = str(row.get("type", "text"))
    title = str(row.get("title", "Untitled"))
    caption = str(row.get("caption", "") or "")
    added_at = str(row.get("added_at", ""))
    added_label = format_added_label(added_at) if added_at else ""
    file_name = row.get("file_name")
    fn = str(file_name) if file_name else None
    stored = row.get("stored_file")
    stored_s = str(stored) if stored else None

    base = str(request.base_url).rstrip("/")
    media_url = f"{base}/cases/{case_id}/contexts/{cid}/media" if stored_s else None

    text_full = row.get("text_full")
    text_preview = None
    text_full_s = None
    if ctype == "text" and text_full is not None:
        text_full_s = str(text_full)
        text_preview = make_text_preview(text_full_s)

    image_src = media_url if ctype == "image" and media_url else None
    video_src = media_url if ctype == "video" and media_url else None
    audio_src = media_url if ctype == "audio" and media_url else None
    document_src = media_url if ctype == "document" and media_url else None
    doc_subtype = row.get("doc_subtype")
    ds = str(doc_subtype) if doc_subtype else None
    src_url = row.get("source_url")
    source_url_out = str(src_url).strip() if src_url else None

    return ContextItemOut(
        id=cid,
        type=ctype,
        title=title,
        caption=caption,
        addedLabel=added_label,
        fileName=fn,
        textPreview=text_preview,
        textFull=text_full_s,
        imageSrc=image_src,
        videoSrc=video_src,
        audioSrc=audio_src,
        documentSrc=document_src,
        docSubtype=ds,
        uploadedFile=bool(stored_s),
        sourceUrl=source_url_out if ctype == "research" and source_url_out else None,
    )


def _parse_research_source_url(raw: str) -> str:
    u = (raw or "").strip()
    if not u:
        raise HTTPException(status_code=400, detail="source_url is required for type research")
    parsed = urlparse(u)
    if parsed.scheme not in ("http", "https") or not parsed.netloc:
        raise HTTPException(status_code=400, detail="source_url must be a valid http(s) URL with a host")
    return u


def _default_title_from_research_url(url: str) -> str:
    parsed = urlparse(url)
    host = (parsed.netloc or "").split("@")[-1]
    if host:
        return host
    return "Research link"


@router.get("", response_model=ContextListOut)
def list_contexts(case_id: str, request: Request, q: str | None = None) -> ContextListOut:
    try:
        validate_case_id(case_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    items = read_catalog(case_id)
    filtered = filter_items_by_query(items, q)
    filtered.sort(key=lambda x: str(x.get("added_at", "")), reverse=True)
    return ContextListOut(
        items=[_catalog_to_response_item(request, case_id, row) for row in filtered],
    )


@router.post("", response_model=ContextItemOut)
async def create_context(
    case_id: str,
    request: Request,
    background_tasks: BackgroundTasks,
    file: UploadFile | None = File(None),
    title: str = Form(""),
    caption: str = Form(""),
    context_type: str = Form(""),
    text_full: str = Form(""),
    doc_subtype: str = Form(""),
    source_url: str = Form(""),
) -> ContextItemOut:
    try:
        validate_case_id(case_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e

    ctype = (context_type or "").strip().lower()
    if not ctype:
        raise HTTPException(status_code=400, detail="context_type is required")
    if ctype not in ALLOWED_TYPES:
        raise HTTPException(status_code=400, detail=f"Unsupported context_type: {ctype}")

    paths = context_library_paths(case_id)
    catalog = read_catalog(case_id)
    item_id = new_context_id()
    added_at = datetime.now(timezone.utc).isoformat()

    row: dict[str, Any] = {
        "id": item_id,
        "type": ctype,
        "title": title.strip() or ("Untitled note" if ctype == "text" else "Untitled"),
        "caption": caption.strip(),
        "added_at": added_at,
        "file_name": None,
        "stored_file": None,
        "text_full": None,
        "doc_subtype": None,
        "source_url": None,
    }

    if ctype == "text":
        body = text_full.replace("\r\n", "\n") if text_full else ""
        if not body.strip():
            raise HTTPException(status_code=400, detail="text_full is required for type text")
        row["text_full"] = body
        row["title"] = title.strip() or "Untitled note"
    elif ctype == "research":
        url = _parse_research_source_url(source_url)
        row["source_url"] = url
        row["title"] = title.strip() or _default_title_from_research_url(url)
    else:
        if file is None or not file.filename:
            raise HTTPException(status_code=400, detail="file is required for non-text context types")
        suffix = Path(file.filename).suffix or ".bin"
        safe_suffix = suffix if len(suffix) <= 16 and "/" not in suffix and "\\" not in suffix else ".bin"
        stored_name = f"{item_id}{safe_suffix}"
        dest = paths["files"] / stored_name
        try:
            content = await file.read()
            dest.write_bytes(content)
        finally:
            await file.close()
        row["file_name"] = file.filename
        row["stored_file"] = stored_name
        row["title"] = title.strip() or (file.filename or "Untitled")
        if ctype == "document" and doc_subtype.strip():
            row["doc_subtype"] = doc_subtype.strip().lower()

    catalog.append(row)
    write_catalog(case_id, catalog)
    # Research links are library-only; RAG for web material is handled by live session "Save to context".
    if ctype != "research":
        background_tasks.add_task(background_ingest_context_to_rag, case_id, dict(row))
    return _catalog_to_response_item(request, case_id, row)


@router.delete("/{item_id}")
def delete_context(case_id: str, item_id: str) -> dict[str, str]:
    try:
        validate_case_id(case_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    if not item_id or ".." in item_id:
        raise HTTPException(status_code=400, detail="Invalid item_id")

    catalog = read_catalog(case_id)
    found: dict | None = None
    rest: list[dict] = []
    for row in catalog:
        if str(row.get("id")) == item_id:
            found = row
        else:
            rest.append(row)
    if found is None:
        raise HTTPException(status_code=404, detail="Context item not found")

    stored = found.get("stored_file")
    if stored:
        paths = context_library_paths(case_id)
        fp = paths["files"] / str(stored)
        try:
            fp.unlink(missing_ok=True)
        except OSError:
            pass

    rag_doc = found.get("rag_doc_id")
    if rag_doc:
        rid = str(rag_doc).strip()
        if rid:
            from rag.vector_store import delete_chunks_for_doc_id

            delete_chunks_for_doc_id(rid)
            delete_stored_document_files(case_id, rid)

    write_catalog(case_id, rest)
    return {"status": "deleted", "id": item_id}


@router.get("/{item_id}/media")
def get_context_media(case_id: str, item_id: str):
    try:
        validate_case_id(case_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    if not item_id or ".." in item_id:
        raise HTTPException(status_code=400, detail="Invalid item_id")

    catalog = read_catalog(case_id)
    row = next((r for r in catalog if str(r.get("id")) == item_id), None)
    if row is None:
        raise HTTPException(status_code=404, detail="Context item not found")
    stored = row.get("stored_file")
    if not stored:
        raise HTTPException(status_code=404, detail="No media for this item")

    paths = context_library_paths(case_id)
    fp = paths["files"] / str(stored)
    if not fp.is_file():
        raise HTTPException(status_code=404, detail="Media file missing")

    mime, _ = mimetypes.guess_type(str(fp))
    media_type = mime or "application/octet-stream"
    # Omit filename so Starlette does not set Content-Disposition. Safari is prone to showing
    # "Save As" for PDF iframes when inline responses include filename=; embed + fetch still work.
    return FileResponse(
        path=str(fp),
        filename=None,
        media_type=media_type,
        content_disposition_type="inline",
    )
