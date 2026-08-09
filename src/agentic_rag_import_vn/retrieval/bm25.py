from __future__ import annotations

import json
import math
import re
from collections import Counter, defaultdict
from pathlib import Path

import pandas as pd

from agentic_rag_import_vn.config import settings
from agentic_rag_import_vn.io_utils import ensure_dirs, read_table


TOKEN_RE = re.compile(r"[\w\d]+", re.UNICODE)


def tokenize(text: str) -> list[str]:
    return TOKEN_RE.findall(str(text).lower())


def json_clean(value: object) -> object:
    if value is None:
        return None
    if isinstance(value, float):
        if math.isnan(value) or math.isinf(value):
            return None
        if value.is_integer():
            return int(value)
        return value
    try:
        if pd.isna(value):
            return None
    except Exception:
        pass
    return value


def build_index(chunks: pd.DataFrame) -> dict[str, object]:
    docs = []
    df_counter: Counter[str] = Counter()
    tokenized_docs: list[list[str]] = []
    for _, row in chunks.iterrows():
        tokens = tokenize(row["text"])
        tokenized_docs.append(tokens)
        df_counter.update(set(tokens))
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
    return {
        "docs": docs,
        "tokens": tokenized_docs,
        "df": dict(df_counter),
        "avgdl": sum(len(tokens) for tokens in tokenized_docs) / max(len(tokenized_docs), 1),
    }


def save_index(index: dict[str, object], path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(index, ensure_ascii=False, allow_nan=False), encoding="utf-8")
    return path


def load_index(path: Path | None = None) -> dict[str, object]:
    path = path or settings.indexes_dir / "bm25" / "legal_index.json"
    return json.loads(path.read_text(encoding="utf-8"))


def run_build_bm25() -> Path:
    ensure_dirs([settings.indexes_dir / "bm25"])
    chunks = read_table(settings.curated_dir / "legal" / "legal_chunks.parquet")
    if not chunks.empty and "quality_status" in chunks.columns:
        chunks = chunks[chunks["quality_status"] == "pass"].copy()
    index = build_index(chunks)
    return save_index(index, settings.indexes_dir / "bm25" / "legal_index.json")


def search(query: str, top_k: int = 5, index_path: Path | None = None) -> list[dict[str, object]]:
    index = load_index(index_path)
    docs = index["docs"]
    tokenized_docs = index["tokens"]
    df = index["df"]
    avgdl = float(index["avgdl"] or 1.0)
    query_terms = tokenize(query)
    if not query_terms:
        return []

    n_docs = max(len(docs), 1)
    scores: defaultdict[int, float] = defaultdict(float)
    k1 = 1.5
    b = 0.75
    for term in query_terms:
        doc_freq = int(df.get(term, 0))
        if doc_freq == 0:
            continue
        idf = math.log(1 + (n_docs - doc_freq + 0.5) / (doc_freq + 0.5))
        for doc_index, tokens in enumerate(tokenized_docs):
            freq = tokens.count(term)
            if not freq:
                continue
            dl = len(tokens) or 1
            score = idf * (freq * (k1 + 1)) / (freq + k1 * (1 - b + b * dl / avgdl))
            scores[doc_index] += score

    ranked = sorted(scores.items(), key=lambda item: item[1], reverse=True)[:top_k]
    return [{**docs[index], "score": score} for index, score in ranked]
