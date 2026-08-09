from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
from tqdm import tqdm

from agentic_rag_import_vn.config import settings
from agentic_rag_import_vn.io_utils import ensure_dirs, read_table, write_table


TEXT_CATEGORIES = {"legal", "origin", "vat", "hs", "tariff"}
TEXT_EXTENSIONS = {"pdf", "docx", "xlsx", "xls", "csv", "txt"}


def extract_pdf(path: Path) -> list[dict[str, object]]:
    from pypdf import PdfReader

    rows: list[dict[str, object]] = []
    reader = PdfReader(str(path))
    for index, page in enumerate(reader.pages, start=1):
        text = page.extract_text() or ""
        rows.append({"page": index, "section": None, "text": text.strip()})
    return rows


def extract_docx(path: Path) -> list[dict[str, object]]:
    from docx import Document

    doc = Document(str(path))
    text = "\n".join(p.text.strip() for p in doc.paragraphs if p.text.strip())
    for table in doc.tables:
        for row in table.rows:
            values = [cell.text.strip() for cell in row.cells]
            if any(values):
                text += "\n" + " | ".join(values)
    return [{"page": None, "section": None, "text": text.strip()}]


def extract_spreadsheet(path: Path) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    sheets = pd.read_excel(path, sheet_name=None, dtype=str, header=None)
    for sheet_name, df in sheets.items():
        df = df.dropna(how="all")
        lines = []
        for _, row in df.iterrows():
            values = [str(value).strip() for value in row.tolist() if pd.notna(value) and str(value).strip()]
            if values:
                lines.append(" | ".join(values))
        rows.append({"page": None, "section": str(sheet_name), "text": "\n".join(lines)})
    return rows


def extract_csv(path: Path) -> list[dict[str, object]]:
    df = pd.read_csv(path, dtype=str)
    lines = []
    for _, row in df.fillna("").iterrows():
        values = [str(value).strip() for value in row.tolist() if str(value).strip()]
        if values:
            lines.append(" | ".join(values))
    return [{"page": None, "section": None, "text": "\n".join(lines)}]


def extract_text_file(path: Path) -> list[dict[str, object]]:
    return [{"page": None, "section": None, "text": path.read_text(encoding="utf-8", errors="ignore")}]


def extract_document(path: Path, file_type: str) -> list[dict[str, object]]:
    if file_type == "pdf":
        return extract_pdf(path)
    if file_type == "docx":
        return extract_docx(path)
    if file_type in {"xlsx", "xls"}:
        return extract_spreadsheet(path)
    if file_type == "csv":
        return extract_csv(path)
    if file_type == "txt":
        return extract_text_file(path)
    raise ValueError(f"Unsupported text extraction type: {file_type}")


def run_text_extraction(limit: int | None = None) -> Path:
    ensure_dirs([settings.interim_dir / "page_text", settings.manifests_dir])
    registry = read_table(settings.processed_dir / "document_registry.parquet")
    candidates = registry[
        registry["category"].isin(TEXT_CATEGORIES)
        & registry["file_type"].isin(TEXT_EXTENSIONS)
        & registry["duplicate_of"].isna()
    ].copy()
    if limit:
        candidates = candidates.head(limit)

    output_path = settings.interim_dir / "page_text" / "documents.jsonl"
    errors: list[dict[str, object]] = []
    with output_path.open("w", encoding="utf-8") as out:
        for _, row in tqdm(candidates.iterrows(), total=len(candidates), desc="extract-text"):
            file_path = settings.project_root / str(row["relative_path"])
            try:
                pages = extract_document(file_path, str(row["file_type"]))
            except Exception as exc:
                errors.append(
                    {
                        "document_id": row["document_id"],
                        "relative_path": row["relative_path"],
                        "stage": "extract_text",
                        "error": repr(exc),
                    }
                )
                continue
            for page in pages:
                text = str(page.get("text") or "").strip()
                if not text:
                    continue
                out.write(
                    json.dumps(
                        {
                            "document_id": row["document_id"],
                            "title": row["title"],
                            "relative_path": row["relative_path"],
                            "category": row["category"],
                            "agreement": row.get("agreement"),
                            "page": page.get("page"),
                            "section": page.get("section"),
                            "text": text,
                        },
                        ensure_ascii=False,
                    )
                    + "\n"
                )

    if errors:
        write_table(pd.DataFrame(errors), settings.manifests_dir / "ingestion_errors.parquet")
    return output_path
