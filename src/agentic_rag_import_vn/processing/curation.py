from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from agentic_rag_import_vn.config import settings
from agentic_rag_import_vn.io_utils import ensure_dirs, write_table
from agentic_rag_import_vn.quality.audit import finish_run, new_run, write_events, write_processing_run


CURATABLE_LEGAL_ROLES = {"legal_general", "origin_legal", "vat_legal"}


def load_parsed_pages(path: Path | None = None) -> pd.DataFrame:
    path = path or settings.interim_dir / "parsed_json" / "pages.jsonl"
    if not path.exists():
        raise FileNotFoundError(f"Run extract-text first: {path}")
    records = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    return pd.DataFrame(records)


def page_text(page: dict[str, object]) -> str:
    return "\n".join(str(block.get("text") or "") for block in page.get("blocks", [])).strip()


def run_curate_legal() -> Path:
    run = new_run("curate_legal")
    ensure_dirs([settings.curated_dir / "legal", settings.quarantine_dir / "pages", settings.reports_dir / "validation"])
    pages = load_parsed_pages()
    if pages.empty:
        output = settings.curated_dir / "legal" / "legal_pages.parquet"
        write_table(pd.DataFrame(), output)
        return output

    rows: list[dict[str, object]] = []
    quarantine_rows: list[dict[str, object]] = []
    for _, page in pages.iterrows():
        quality = page.get("quality") or {}
        if not isinstance(quality, dict):
            quality = {}
        role = page.get("document_role")
        text = page_text(page.to_dict())
        base = {
            "document_id": page.get("document_id"),
            "title": page.get("title"),
            "relative_path": page.get("relative_path"),
            "category": page.get("category"),
            "document_role": role,
            "agreement": page.get("agreement"),
            "page": page.get("page"),
            "section": page.get("section"),
            "text": text,
            "text_source": page.get("text_source"),
            "parser": page.get("parser"),
            "parser_version": page.get("parser_version"),
            "quality_status": quality.get("quality_status") or quality.get("status"),
            "char_count": quality.get("char_count"),
            "word_count": quality.get("word_count"),
            "provenance_quality": "pass",
            "temporal_quality": "unknown",
            "curated_at": datetime.now(timezone.utc).isoformat(),
        }
        if role in CURATABLE_LEGAL_ROLES and base["quality_status"] == "pass" and len(text) >= 40:
            rows.append(base)
        else:
            quarantine_rows.append({**base, "quarantine_reason": "not_eligible_for_legal_curated_index"})

    output = write_table(pd.DataFrame(rows), settings.curated_dir / "legal" / "legal_pages.parquet")
    quarantine_output = write_table(pd.DataFrame(quarantine_rows), settings.quarantine_dir / "pages" / "non_curated_pages.parquet")
    report_lines = [
        "# Legal Curation Report",
        "",
        f"- Parsed pages: {len(pages):,}",
        f"- Curated legal pages: {len(rows):,}",
        f"- Quarantined/non-indexable pages: {len(quarantine_rows):,}",
        "",
        "Only pages with `quality_status = pass` and legal narrative roles are promoted to `data/curated/legal`.",
    ]
    report_path = settings.reports_dir / "validation" / "legal_curation.md"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text("\n".join(report_lines) + "\n", encoding="utf-8")
    write_processing_run(
        finish_run(run, metrics={"curated_pages": len(rows), "quarantine_pages": len(quarantine_rows)})
    )
    write_events(
        [
            {
                "run_id": run["run_id"],
                "stage": "curate_legal",
                "event_type": "artifact_written",
                "artifact": str(output),
                "created_at": datetime.now(timezone.utc).isoformat(),
            },
            {
                "run_id": run["run_id"],
                "stage": "curate_legal",
                "event_type": "quarantine_written",
                "artifact": str(quarantine_output),
                "created_at": datetime.now(timezone.utc).isoformat(),
            },
        ]
    )
    return output
