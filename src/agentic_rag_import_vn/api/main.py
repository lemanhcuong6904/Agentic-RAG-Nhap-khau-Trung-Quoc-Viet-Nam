from __future__ import annotations

from datetime import date

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from agentic_rag_import_vn.agents.orchestrator import answer_query
from agentic_rag_import_vn.processing.vnaccs import search_vnaccs
from agentic_rag_import_vn.retrieval.bm25 import search as legal_search
from agentic_rag_import_vn.tools.sources import get_source

app = FastAPI(title="Agentic RAG Import VN", version="0.1.0")


class SearchRequest(BaseModel):
    q: str = Field(min_length=1)
    top_k: int = Field(default=5, ge=1, le=50)


class ChatRequest(BaseModel):
    message: str = Field(min_length=1)
    query_date: date | None = None


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/sources/{document_id}")
def source(document_id: str) -> dict[str, object]:
    result = get_source(document_id)
    if result is None:
        raise HTTPException(status_code=404, detail="Source not found")
    return result


@app.post("/legal/search")
def search_legal(request: SearchRequest) -> dict[str, object]:
    return {"results": legal_search(request.q, request.top_k)}


@app.get("/vnaccs/search")
def search_vnaccs_endpoint(q: str, top_k: int = 20) -> dict[str, object]:
    return {"results": search_vnaccs(q, top_k)}


@app.post("/chat")
def chat(request: ChatRequest) -> dict[str, object]:
    response = answer_query(request.message, request.query_date)
    return {
        "answer": response.answer,
        "intent": response.intent,
        "confidence": response.confidence,
        "warnings": response.warnings,
        "sources": response.sources,
        "tool_calls": response.tool_calls,
    }
