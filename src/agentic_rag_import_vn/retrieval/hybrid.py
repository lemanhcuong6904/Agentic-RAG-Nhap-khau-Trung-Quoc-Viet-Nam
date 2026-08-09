from __future__ import annotations

from collections import defaultdict

from agentic_rag_import_vn.config import settings
from agentic_rag_import_vn.retrieval.bm25 import search as bm25_search
from agentic_rag_import_vn.retrieval.dense import DenseRetriever


def reciprocal_rank_fusion(result_sets: list[list[dict[str, object]]], k: int = 60) -> list[dict[str, object]]:
    scores: defaultdict[str, float] = defaultdict(float)
    docs: dict[str, dict[str, object]] = {}
    for results in result_sets:
        for rank, hit in enumerate(results, start=1):
            chunk_id = str(hit.get("chunk_id"))
            scores[chunk_id] += 1.0 / (k + rank)
            docs.setdefault(chunk_id, hit)
    ranked = sorted(scores.items(), key=lambda item: item[1], reverse=True)
    return [{**docs[chunk_id], "score": score, "retriever": "hybrid_rrf"} for chunk_id, score in ranked]


def search(query: str, top_k: int = 8) -> list[dict[str, object]]:
    bm25_hits = bm25_search(query, top_k=max(30, top_k))
    if not settings.enable_hybrid_retrieval or not settings.enable_dense_retrieval:
        return bm25_hits[:top_k]
    try:
        dense_hits = DenseRetriever().search(query, top_k=max(30, top_k))
    except FileNotFoundError:
        return bm25_hits[:top_k]
    fused = reciprocal_rank_fusion([bm25_hits, dense_hits])
    return fused[:top_k]
