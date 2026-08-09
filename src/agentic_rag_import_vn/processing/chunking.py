from __future__ import annotations

import re
from pathlib import Path

import pandas as pd

from agentic_rag_import_vn.config import settings
from agentic_rag_import_vn.io_utils import ensure_dirs, write_table


def normalize_space(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def chunk_text(text: str, max_chars: int = 1400, overlap: int = 180) -> list[str]:
    text = normalize_space(text)
    if len(text) <= max_chars:
        return [text] if text else []

    chunks: list[str] = []
    start = 0
    while start < len(text):
        end = min(start + max_chars, len(text))
        if end < len(text):
            sentence_boundary = max(text.rfind(".", start, end), text.rfind(";", start, end))
            if sentence_boundary > start + max_chars // 2:
                end = sentence_boundary + 1
        chunk = text[start:end].strip()
        if chunk:
            chunks.append(chunk)
        if end >= len(text):
            break
        start = max(0, end - overlap)
    return chunks


def run_chunking() -> Path:
    ensure_dirs([settings.processed_dir])
    page_text_path = settings.interim_dir / "page_text" / "documents.jsonl"
    if not page_text_path.exists():
        raise FileNotFoundError(f"Run extract-text first: {page_text_path}")

    pages = pd.read_json(page_text_path, lines=True)
    rows: list[dict[str, object]] = []
    for _, row in pages.iterrows():
        for index, chunk in enumerate(chunk_text(str(row["text"])), start=1):
            rows.append(
                {
                    "chunk_id": f"{row['document_id']}-{row.get('page') or row.get('section') or 0}-{index}",
                    "document_id": row["document_id"],
                    "title": row["title"],
                    "relative_path": row["relative_path"],
                    "category": row["category"],
                    "agreement": row.get("agreement"),
                    "page": row.get("page"),
                    "section": row.get("section"),
                    "chunk_index": index,
                    "text": chunk,
                }
            )

    return write_table(pd.DataFrame(rows), settings.processed_dir / "legal_chunks.parquet")
