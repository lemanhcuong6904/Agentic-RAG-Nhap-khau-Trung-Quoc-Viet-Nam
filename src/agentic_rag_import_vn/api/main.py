from __future__ import annotations

from datetime import date

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from agentic_rag_import_vn.config import settings
from agentic_rag_import_vn.agents.orchestrator import answer_query
from agentic_rag_import_vn.tools.legal import search_legal_documents
from agentic_rag_import_vn.tools.sources import get_source, get_source_tool
from agentic_rag_import_vn.tools.vnaccs import lookup_vnaccs

app = FastAPI(title="Agentic RAG Import VN", version="0.1.0")


class SearchRequest(BaseModel):
    q: str = Field(min_length=1)
    top_k: int = Field(default=5, ge=1, le=50)


class ChatRequest(BaseModel):
    message: str = Field(min_length=1)
    query_date: date | None = None
    include_state: bool = False


class VnaccsRequest(BaseModel):
    q: str = Field(min_length=1)
    code_type: str | None = None
    code_group: str | None = None
    limit: int = Field(default=20, ge=1, le=100)


@app.get("/health")
def health() -> dict[str, object]:
    return {
        "status": "ok",
        "environment": settings.app_env,
        "capabilities": {
            "legal": settings.enable_legal,
            "vnaccs": settings.enable_vnaccs,
            "hs": settings.enable_hs,
            "tariff": settings.enable_tariff,
            "origin_psr": settings.enable_origin_psr,
            "statistics": settings.enable_statistics,
            "dense_retrieval": settings.enable_dense_retrieval,
            "hybrid_retrieval": settings.enable_hybrid_retrieval,
            "reranker": settings.enable_reranker,
        },
        "models": {
            "llm_provider": settings.llm_provider,
            "llm_model": settings.llm_model,
            "llm_ready": bool(settings.openai_api_key),
            "embedding_provider": settings.embedding_provider,
            "embedding_model": settings.embedding_model,
        },
    }


@app.get("/sources/{document_id}")
def source(document_id: str) -> dict[str, object]:
    result = get_source(document_id)
    if result is None:
        raise HTTPException(status_code=404, detail="Source not found")
    return result


@app.post("/legal/search")
def search_legal(request: SearchRequest) -> dict[str, object]:
    return search_legal_documents(request.q, top_k=request.top_k).model_dump(mode="json")


@app.get("/vnaccs/search")
def search_vnaccs_endpoint(q: str, top_k: int = 20) -> dict[str, object]:
    return lookup_vnaccs(q, limit=top_k).model_dump(mode="json")


@app.post("/vnaccs/search")
def search_vnaccs_post(request: VnaccsRequest) -> dict[str, object]:
    return lookup_vnaccs(request.q, code_type=request.code_type, code_group=request.code_group, limit=request.limit).model_dump(mode="json")


@app.get("/sources/{document_id}/quality")
def source_quality(document_id: str) -> dict[str, object]:
    result = get_source_tool(document_id)
    if result.status == "not_found":
        raise HTTPException(status_code=404, detail="Source not found")
    return result.model_dump(mode="json")


@app.post("/chat")
def chat(request: ChatRequest) -> dict[str, object]:
    response = answer_query(request.message, request.query_date)
    payload = {
        "answer": response.answer,
        "intent": response.intent,
        "confidence": response.confidence,
        "warnings": response.warnings,
        "sources": response.sources,
        "tool_calls": response.tool_calls,
    }
    if request.include_state:
        payload["state"] = response.state
    return payload
