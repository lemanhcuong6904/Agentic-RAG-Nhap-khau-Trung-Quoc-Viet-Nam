from __future__ import annotations

from agentic_rag_import_vn.config import settings
from agentic_rag_import_vn.repositories.legal import LegalRepository
from agentic_rag_import_vn.schemas import ToolResult


def search_legal_documents(
    query: str,
    *,
    agreement: str | None = None,
    document_role: list[str] | None = None,
    top_k: int = 8,
) -> ToolResult:
    if not settings.enable_legal:
        return ToolResult(status="unavailable", warnings=["Legal search capability is disabled."])
    try:
        repo = LegalRepository()
        hits = repo.search(query, agreement=agreement, document_role=document_role, top_k=top_k)
    except Exception as exc:
        return ToolResult(status="error", errors=[repr(exc)])
    evidence = [repo.to_evidence(hit) for hit in hits]
    warnings = []
    if not hits:
        return ToolResult(status="not_found", warnings=["No curated legal evidence matched the query."])
    if any(item.temporal_quality == "unknown" for item in evidence):
        warnings.append("Some legal sources have unknown temporal/effectivity metadata.")
    return ToolResult(status="success", data=hits, evidence=evidence, warnings=warnings)
