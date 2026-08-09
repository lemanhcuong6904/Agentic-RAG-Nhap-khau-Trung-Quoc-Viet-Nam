from __future__ import annotations

from agentic_rag_import_vn.config import settings
from agentic_rag_import_vn.io_utils import read_table


class SourceRepository:
    def get(self, document_id: str, page: int | None = None) -> dict[str, object] | None:
        registry = read_table(settings.processed_dir / "document_registry.parquet")
        match = registry[registry["document_id"].astype(str) == document_id]
        if match.empty:
            return None
        record = match.fillna("").iloc[0].to_dict()
        record["page"] = page
        record["quality"] = {
            "metadata": record.get("metadata_quality"),
            "provenance": record.get("provenance_quality"),
            "temporal": record.get("temporal_quality"),
        }
        return record
