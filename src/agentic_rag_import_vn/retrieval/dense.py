from __future__ import annotations

import json
from pathlib import Path

import numpy as np

from agentic_rag_import_vn.config import settings
from agentic_rag_import_vn.io_utils import ensure_dirs, read_table
from agentic_rag_import_vn.retrieval.bm25 import json_clean


def load_embedding_model(*, local_files_only: bool = False):
    if settings.embedding_provider != "sentence_transformers":
        raise RuntimeError(f"Unsupported embedding provider: {settings.embedding_provider}")
    from sentence_transformers import SentenceTransformer

    return SentenceTransformer(settings.embedding_model, local_files_only=local_files_only)


def dense_index_paths() -> tuple[Path, Path]:
    base = settings.indexes_dir / "vector" / "legal_bge_m3"
    return base / "embeddings.npy", base / "metadata.json"


def run_build_dense() -> Path:
    if not settings.enable_dense_retrieval:
        raise RuntimeError("Dense retrieval is disabled by RAG_ENABLE_DENSE_RETRIEVAL=false")
    ensure_dirs([settings.indexes_dir / "vector" / "legal_bge_m3"])
    chunks = read_table(settings.curated_dir / "legal" / "legal_chunks.parquet")
    if not chunks.empty and "quality_status" in chunks.columns:
        chunks = chunks[chunks["quality_status"] == "pass"].copy()
    texts = chunks["text"].fillna("").astype(str).tolist()
    model = load_embedding_model()
    embeddings = model.encode(texts, normalize_embeddings=True, show_progress_bar=True)
    embeddings = np.asarray(embeddings, dtype=np.float32)
    vectors_path, metadata_path = dense_index_paths()
    np.save(vectors_path, embeddings)
    docs = []
    for _, row in chunks.iterrows():
        docs.append(
            {
                "chunk_id": json_clean(row["chunk_id"]),
                "document_id": json_clean(row["document_id"]),
                "title": json_clean(row["title"]),
                "relative_path": json_clean(row["relative_path"]),
                "category": json_clean(row["category"]),
                "document_role": json_clean(row.get("document_role")),
                "agreement": json_clean(row.get("agreement")),
                "page": json_clean(row.get("page")),
                "section": json_clean(row.get("section")),
                "quality_status": json_clean(row.get("quality_status")),
                "provenance_quality": json_clean(row.get("provenance_quality")),
                "temporal_quality": json_clean(row.get("temporal_quality")),
                "text": json_clean(row["text"]),
            }
        )
    metadata = {
        "embedding_provider": settings.embedding_provider,
        "embedding_model": settings.embedding_model,
        "normalize_embeddings": True,
        "docs": docs,
    }
    metadata_path.write_text(json.dumps(metadata, ensure_ascii=False, allow_nan=False), encoding="utf-8")
    return metadata_path


class DenseRetriever:
    def __init__(self) -> None:
        self.vectors_path, self.metadata_path = dense_index_paths()
        self._model = None
        self._vectors = None
        self._docs = None

    def load(self) -> None:
        if self._vectors is not None:
            return
        if not self.vectors_path.exists() or not self.metadata_path.exists():
            raise FileNotFoundError("Dense index not found. Run `python -m agentic_rag_import_vn.pipeline build-dense`.")
        self._vectors = np.load(self.vectors_path)
        metadata = json.loads(self.metadata_path.read_text(encoding="utf-8"))
        self._docs = metadata["docs"]
        self._model = load_embedding_model(local_files_only=True)

    def search(self, query: str, top_k: int = 20) -> list[dict[str, object]]:
        self.load()
        query_vec = self._model.encode([query], normalize_embeddings=True)
        query_vec = np.asarray(query_vec, dtype=np.float32)[0]
        scores = self._vectors @ query_vec
        if scores.size == 0:
            return []
        top_indices = np.argsort(-scores)[:top_k]
        return [{**self._docs[int(index)], "score": float(scores[int(index)]), "retriever": "dense"} for index in top_indices]
