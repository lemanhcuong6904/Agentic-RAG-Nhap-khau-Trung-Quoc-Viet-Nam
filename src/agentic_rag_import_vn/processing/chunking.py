from __future__ import annotations

import re
from pathlib import Path

import pandas as pd

from agentic_rag_import_vn.config import settings
from agentic_rag_import_vn.io_utils import ensure_dirs, read_table, write_table


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
    ensure_dirs([settings.processed_dir, settings.curated_dir / "legal"])
    pages_path = settings.curated_dir / "legal" / "legal_pages.parquet"
    if not pages_path.exists():
        raise FileNotFoundError(f"Run curate-legal first: {pages_path}")

    pages = read_table(pages_path)
    rows: list[dict[str, object]] = []
    for _, row in pages.iterrows():
        for index, chunk in enumerate(chunk_text(str(row["text"])), start=1):
            fingerprint = f"{row['document_id']}:{row.get('page') or row.get('section') or 0}:{index}:{len(chunk)}"
            rows.append(
                {
                    "chunk_id": f"{row['document_id']}-{row.get('page') or row.get('section') or 0}-{index}",
                    "content_fingerprint": fingerprint,
                    "document_id": row["document_id"],
                    "title": row["title"],
                    "relative_path": row["relative_path"],
                    "category": row["category"],
                    "document_role": row.get("document_role"),
                    "agreement": row.get("agreement"),
                    "page": row.get("page"),
                    "section": row.get("section"),
                    "chunk_index": index,
                    "quality_status": row.get("quality_status"),
                    "provenance_quality": row.get("provenance_quality"),
                    "temporal_quality": row.get("temporal_quality"),
                    "text": chunk,
                }
            )

    chunks = pd.DataFrame(rows)
    processed_path = write_table(chunks, settings.processed_dir / "legal_chunks.parquet")
    write_table(chunks, settings.curated_dir / "legal" / "legal_chunks.parquet")
    return processed_path
