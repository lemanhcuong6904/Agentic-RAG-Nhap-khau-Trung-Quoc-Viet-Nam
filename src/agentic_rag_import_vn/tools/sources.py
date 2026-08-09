from __future__ import annotations

from agentic_rag_import_vn.repositories.sources import SourceRepository
from agentic_rag_import_vn.schemas import ToolResult


def get_source(document_id: str, page: int | None = None) -> dict[str, object] | None:
    return SourceRepository().get(document_id, page=page)


def get_source_tool(document_id: str, page: int | None = None) -> ToolResult:
    try:
        source = get_source(document_id, page)
    except Exception as exc:
        return ToolResult(status="error", errors=[repr(exc)])
    if source is None:
        return ToolResult(status="not_found", warnings=["Source not found."])
    warnings = []
    quality = source.get("quality") or {}
    if quality.get("provenance") == "partial":
        warnings.append("Source official URL/download metadata is incomplete.")
    if quality.get("temporal") == "unknown":
        warnings.append("Source temporal/effectivity metadata is unknown.")
    return ToolResult(status="success", data=[source], warnings=warnings)
