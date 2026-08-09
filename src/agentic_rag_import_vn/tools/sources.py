from __future__ import annotations

from agentic_rag_import_vn.config import settings
from agentic_rag_import_vn.io_utils import read_table


def get_source(document_id: str) -> dict[str, object] | None:
    registry = read_table(settings.processed_dir / "document_registry.parquet")
    match = registry[registry["document_id"].astype(str) == document_id]
    if match.empty:
        return None
    return match.fillna("").iloc[0].to_dict()
