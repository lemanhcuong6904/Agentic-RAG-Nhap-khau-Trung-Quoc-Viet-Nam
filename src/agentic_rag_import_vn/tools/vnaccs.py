from __future__ import annotations

from agentic_rag_import_vn.config import settings
from agentic_rag_import_vn.repositories.vnaccs import VnaccsRepository
from agentic_rag_import_vn.schemas import Evidence, ToolResult


def lookup_vnaccs(
    query: str,
    *,
    code_type: str | None = None,
    code_group: str | None = None,
    limit: int = 20,
) -> ToolResult:
    if not settings.enable_vnaccs:
        return ToolResult(status="unavailable", warnings=["VNACCS capability is disabled."])
    try:
        repo = VnaccsRepository()
        rows = repo.lookup(query, code_type=code_type, code_group=code_group, limit=limit)
    except Exception as exc:
        return ToolResult(status="error", errors=[repr(exc)])
    if not rows:
        return ToolResult(status="not_found", warnings=["No VNACCS rows matched the query."])
    evidence = [
        Evidence(
            evidence_id=f"vnaccs:{row.get('source_document_id')}:{row.get('sheet')}:{row.get('row_number')}",
            source="vnaccs_lookup",
            document_id=row.get("source_document_id"),
            title=row.get("source_title"),
            path=row.get("source_path"),
            text=f"{row.get('code')}: {row.get('description')}",
            quality_status=row.get("quality_status"),
            provenance_quality=row.get("provenance_quality"),
        )
        for row in rows
    ]
    status = "ambiguous" if len({row.get("code_group") for row in rows}) > 1 else "success"
    warnings = []
    if status == "ambiguous":
        warnings.append("The same code or keyword appears in multiple VNACCS code groups; use code_type/code_group to narrow it.")
    return ToolResult(status=status, data=rows, evidence=evidence, warnings=warnings)
