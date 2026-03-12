from __future__ import annotations

import uuid
from datetime import date, datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class FilingStatus(str, Enum):
    PENDING = "pending"
    INGESTED = "ingested"
    TRANSFORMED = "transformed"
    EMBEDDED = "embedded"
    FAILED = "failed"


class FormType(str, Enum):
    TEN_K = "10-K"
    TEN_Q = "10-Q"


class PipelineStage(str, Enum):
    INGESTION = "ingestion"
    TRANSFORM = "transform"
    EMBEDDING = "embedding"


class Section(str, Enum):
    BUSINESS = "business"
    RISK_FACTORS = "risk_factors"
    MDA = "mda"
    FINANCIALS = "financials"
    CONTROLS = "controls"
    LEGAL = "legal"
    MARKET = "market"
    SELECTED_DATA = "selected_data"


# ---------------------------------------------------------------------------
# Domain entities
# ---------------------------------------------------------------------------


class Tenant(BaseModel):
    id: uuid.UUID
    name: str
    api_key_hash: str
    ticker_universe: list[str]
    created_at: datetime


class Filing(BaseModel):
    id: uuid.UUID
    accession_number: str
    ticker: str
    cik: str
    form_type: str
    period_of_report: date
    filed_date: date
    raw_s3_key: str | None = None
    parquet_s3_key: str | None = None
    status: FilingStatus = FilingStatus.PENDING
    error_message: str | None = None
    created_at: datetime
    updated_at: datetime


class FilingChunk(BaseModel):
    id: uuid.UUID | None = None
    filing_id: uuid.UUID
    chunk_index: int
    section: str
    content: str
    token_count: int
    embedding: list[float] | None = None
    ticker: str
    form_type: str
    period_of_report: date
    created_at: datetime | None = None


class QualityCheck(BaseModel):
    name: str
    passed: bool
    value: Any = None
    threshold: Any = None
    message: str | None = None


class QualityReport(BaseModel):
    filing_id: uuid.UUID
    stage: PipelineStage
    passed: bool
    checks: list[QualityCheck]


# ---------------------------------------------------------------------------
# API request/response models
# ---------------------------------------------------------------------------


class IngestRequest(BaseModel):
    ticker: str
    date_from: str = Field(description="ISO date string YYYY-MM-DD")
    date_to: str = Field(description="ISO date string YYYY-MM-DD")


class QueryRequest(BaseModel):
    query: str = Field(max_length=2000)
    stream: bool = False


class RetrievedChunk(BaseModel):
    chunk_id: uuid.UUID
    filing_id: uuid.UUID
    ticker: str
    form_type: str
    period_of_report: date
    section: str
    content: str
    score: float


class ToolCall(BaseModel):
    tool_name: str
    inputs: dict[str, Any]
    outputs: Any
    latency_ms: int


class AgentResponse(BaseModel):
    query: str
    answer: str
    sources: list[RetrievedChunk]
    tool_calls: list[ToolCall]
    input_tokens: int
    output_tokens: int
    latency_ms: int


class FilingListResponse(BaseModel):
    filings: list[Filing]
    total: int
    page: int
    page_size: int


class HealthResponse(BaseModel):
    status: str
    version: str = "0.1.0"


class ReadyResponse(BaseModel):
    status: str
    checks: dict[str, bool]


# ---------------------------------------------------------------------------
# Parquet row schema (dataclass-like for PyArrow)
# ---------------------------------------------------------------------------


class ParquetChunkRow(BaseModel):
    filing_id: str
    accession_number: str
    ticker: str
    form_type: str
    period_of_report: str  # ISO date
    filed_date: str  # ISO date
    section: str
    chunk_index: int
    content: str
    token_count: int
    char_count: int
    has_tables: bool
    quality_score: float
    pipeline_version: str
    created_at: str  # ISO datetime
