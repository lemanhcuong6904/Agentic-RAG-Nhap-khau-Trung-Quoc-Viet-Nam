from __future__ import annotations

from datetime import date
from typing import Literal

from pydantic import BaseModel, Field


ToolStatus = Literal["success", "partial", "not_found", "ambiguous", "unavailable", "error"]


class Evidence(BaseModel):
    evidence_id: str
    source: str
    document_id: str | None = None
    title: str | None = None
    path: str | None = None
    page: int | None = None
    chunk_id: str | None = None
    text: str | None = None
    score: float | None = None
    quality_status: str | None = None
    provenance_quality: str | None = None
    temporal_quality: str | None = None


class ToolResult(BaseModel):
    status: ToolStatus
    data: list[dict] = Field(default_factory=list)
    evidence: list[Evidence] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)


class ToolCallTrace(BaseModel):
    tool: str
    args: dict = Field(default_factory=dict)
    status: ToolStatus
    rows: int = 0
    warnings: list[str] = Field(default_factory=list)


class VerificationResult(BaseModel):
    status: Literal["pass", "warning", "fail"]
    warnings: list[str] = Field(default_factory=list)
    unsupported_claims: list[str] = Field(default_factory=list)


class ImportAdvisoryState(BaseModel):
    request_id: str
    session_id: str | None = None
    query: str
    query_date: date | None = None
    intents: list[str] = Field(default_factory=list)
    requested_tasks: list[str] = Field(default_factory=list)
    plan: list[dict] = Field(default_factory=list)
    missing_fields: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    evidence_pool: list[Evidence] = Field(default_factory=list)
    legal_evidence: list[dict] = Field(default_factory=list)
    vnaccs_results: list[dict] = Field(default_factory=list)
    verification: VerificationResult | None = None
    final_answer: str | None = None
    tool_trace: list[ToolCallTrace] = Field(default_factory=list)
    retry_count: int = 0
