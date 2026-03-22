from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, field_validator


# --- Source / enums ---
SourceLiteral = Literal["upload", "tts", "web"]
ChunkTypeLiteral = Literal["raw", "summary", "event", "claim"]
StructuredHitTypeLiteral = Literal["event", "claim", "summary"]


# -----------------------------------------------------------------------------
# 1. DOCUMENT
# -----------------------------------------------------------------------------


class StoreDocumentRequest(BaseModel):
    """INPUT to POST /store (no doc_id)."""

    case_id: str
    raw_text: str
    source: SourceLiteral = "upload"
    timestamp: str | datetime | None = None
    # When set (e.g. live session save), persisted on disk in metadata for context library links.
    source_url: str | None = None

    @field_validator("timestamp", mode="before")
    @classmethod
    def coerce_timestamp(cls, v: str | datetime | None) -> str | None:
        if v is None:
            return None
        if isinstance(v, datetime):
            return v.isoformat()
        return v


class Document(BaseModel):
    """Full document (internal, /parse input, ingest.document)."""

    case_id: str
    doc_id: str
    raw_text: str
    source: SourceLiteral = "upload"
    timestamp: str  # ISO-8601
    source_url: str | None = None

    @field_validator("timestamp", mode="before")
    @classmethod
    def coerce_timestamp(cls, v: str | datetime) -> str:
        if isinstance(v, datetime):
            return v.isoformat()
        return v


# -----------------------------------------------------------------------------
# 2. STRUCTURED DOCUMENT (/parse output)
# -----------------------------------------------------------------------------


_PARTY_ROLES = frozenset({"plaintiff", "defendant", "other"})


class Party(BaseModel):
    name: str = ""
    role: Literal["plaintiff", "defendant", "other"] = "other"
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)

    @field_validator("role", mode="before")
    @classmethod
    def coerce_party_role(cls, v: object) -> str:
        """LLMs often emit labels like 'contracting' or 'party'; only three roles are legal."""
        if v is None:
            return "other"
        s = str(v).strip().lower()
        if s in _PARTY_ROLES:
            return s
        return "other"


class Event(BaseModel):
    event: str = ""
    date: str | None = None
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    source_span: str = ""


class Claim(BaseModel):
    type: str = ""
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    source_span: str = ""


class JurisdictionBlock(BaseModel):
    value: str = ""
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)


class Damage(BaseModel):
    type: str = ""
    amount: str | None = None
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    source_span: str = ""


class SummaryBlock(BaseModel):
    text: str = ""
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)


class StructuredDocument(BaseModel):
    doc_id: str
    case_id: str
    parties: list[Party] = Field(default_factory=list)
    events: list[Event] = Field(default_factory=list)
    claims: list[Claim] = Field(default_factory=list)
    jurisdiction: JurisdictionBlock = Field(default_factory=JurisdictionBlock)
    damages: list[Damage] = Field(default_factory=list)
    summary: SummaryBlock = Field(default_factory=SummaryBlock)


# Back-compat alias for internal imports
StructuredDoc = StructuredDocument


# -----------------------------------------------------------------------------
# Store / ingest responses
# -----------------------------------------------------------------------------


class StoreResponse(BaseModel):
    doc_id: str
    status: Literal["stored"] = "stored"
    num_chunks: int
    summary: str = ""


class IngestRequest(BaseModel):
    document: Document
    structured: StructuredDocument


class IngestResponse(BaseModel):
    num_chunks: int
    doc_id: str


# -----------------------------------------------------------------------------
# 4–5. QUERY INPUT & QUERY RESULT
# -----------------------------------------------------------------------------


class QueryFilters(BaseModel):
    type: ChunkTypeLiteral | None = None


class QueryInput(BaseModel):
    case_id: str
    query: str
    top_k: int = Field(default=5, ge=1, le=30)
    filters: QueryFilters = Field(default_factory=QueryFilters)


class ChunkMetadataOut(BaseModel):
    source: str
    timestamp: str
    type: str


class ChunkResult(BaseModel):
    chunk_id: str
    doc_id: str
    text: str
    score: float
    metadata: ChunkMetadataOut


class StructuredHitOut(BaseModel):
    type: StructuredHitTypeLiteral
    value: str
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    doc_id: str


class QueryResult(BaseModel):
    query: str
    chunks: list[ChunkResult]
    structured_hits: list[StructuredHitOut]
    sources: list[str]
