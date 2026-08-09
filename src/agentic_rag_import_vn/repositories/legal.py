from __future__ import annotations

from agentic_rag_import_vn.config import settings
from agentic_rag_import_vn.retrieval.bm25 import search as bm25_search
from agentic_rag_import_vn.retrieval.hybrid import search as hybrid_search
from agentic_rag_import_vn.retrieval.query_expansion import expand_query
from agentic_rag_import_vn.schemas import Evidence


class LegalRepository:
    def search(
        self,
        query: str,
        *,
        agreement: str | None = None,
        document_role: list[str] | None = None,
        top_k: int = 8,
    ) -> list[dict[str, object]]:
        search_fn = hybrid_search if settings.enable_hybrid_retrieval else bm25_search
        hits = search_fn(expand_query(query), top_k=max(top_k * 4, top_k))
        filtered: list[dict[str, object]] = []
        roles = set(document_role or [])
        for hit in hits:
            if agreement and hit.get("agreement") != agreement:
                continue
            if roles and hit.get("document_role") not in roles:
                continue
            if hit.get("quality_status") != "pass":
                continue
            filtered.append(hit)
            if len(filtered) >= top_k:
                break
        return filtered

    @staticmethod
    def to_evidence(hit: dict[str, object]) -> Evidence:
        page = hit.get("page")
        if isinstance(page, float) and page.is_integer():
            page = int(page)
        if not isinstance(page, int):
            page = None
        return Evidence(
            evidence_id=str(hit.get("chunk_id")),
            source="legal_bm25",
            document_id=hit.get("document_id"),
            title=hit.get("title"),
            path=hit.get("relative_path"),
            page=page,
            chunk_id=hit.get("chunk_id"),
            text=hit.get("text"),
            score=float(hit.get("score") or 0.0),
            quality_status=hit.get("quality_status"),
            provenance_quality=hit.get("provenance_quality"),
            temporal_quality=hit.get("temporal_quality"),
        )
