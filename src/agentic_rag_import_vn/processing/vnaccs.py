from __future__ import annotations

from pathlib import Path

import pandas as pd
from tqdm import tqdm

from agentic_rag_import_vn.config import settings
from agentic_rag_import_vn.io_utils import ensure_dirs, read_table, write_table


VNACCS_EXTENSIONS = {"xlsx", "xls", "csv"}


def compact_row(values: list[object]) -> tuple[str | None, str]:
    cleaned = [str(value).strip() for value in values if pd.notna(value) and str(value).strip()]
    if not cleaned:
        return None, ""
    code = cleaned[0]
    description = " | ".join(cleaned[1:]) if len(cleaned) > 1 else ""
    return code, description


def read_workbook_rows(path: Path) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    if path.suffix.lower() == ".csv":
        sheets = {"csv": pd.read_csv(path, dtype=str, header=None)}
    else:
        sheets = pd.read_excel(path, sheet_name=None, dtype=str, header=None)

    for sheet_name, df in sheets.items():
        df = df.dropna(how="all")
        for row_index, row in df.iterrows():
            code, description = compact_row(row.tolist())
            if not code:
                continue
            if code.lower() in {"stt", "mã", "ma", "code"}:
                continue
            rows.append(
                {
                    "sheet": str(sheet_name),
                    "row_number": int(row_index) + 1,
                    "code": code,
                    "description": description,
                    "search_text": f"{code} {description}".strip(),
                }
            )
    return rows


def run_vnaccs_build() -> Path:
    ensure_dirs([settings.processed_dir / "vnaccs_codes", settings.manifests_dir])
    registry = read_table(settings.processed_dir / "document_registry.parquet")
    candidates = registry[
        (registry["category"] == "vnaccs")
        & registry["file_type"].isin(VNACCS_EXTENSIONS)
        & registry["duplicate_of"].isna()
    ].copy()

    all_rows: list[dict[str, object]] = []
    errors: list[dict[str, object]] = []
    for _, doc in tqdm(candidates.iterrows(), total=len(candidates), desc="vnaccs"):
        file_path = settings.project_root / str(doc["relative_path"])
        try:
            rows = read_workbook_rows(file_path)
        except Exception as exc:
            errors.append(
                {
                    "document_id": doc["document_id"],
                    "relative_path": doc["relative_path"],
                    "stage": "build_vnaccs",
                    "error": repr(exc),
                }
            )
            continue
        for row in rows:
            row.update(
                {
                    "source_document_id": doc["document_id"],
                    "source_title": doc["title"],
                    "source_path": doc["relative_path"],
                    "code_group": doc["title"],
                    "status": doc.get("status", "unknown"),
                }
            )
            all_rows.append(row)

    if errors:
        error_path = settings.manifests_dir / "vnaccs_errors.csv"
        write_table(pd.DataFrame(errors), error_path)

    output = settings.processed_dir / "vnaccs_codes" / "vnaccs_codes.parquet"
    return write_table(pd.DataFrame(all_rows), output)


def search_vnaccs(query: str, top_k: int = 20) -> list[dict[str, object]]:
    path = settings.processed_dir / "vnaccs_codes" / "vnaccs_codes.parquet"
    df = read_table(path)
    if df.empty:
        return []
    terms = [term.lower() for term in query.split() if term.strip()]
    if not terms:
        return []
    mask = pd.Series([True] * len(df))
    haystack = df["search_text"].fillna("").str.lower()
    for term in terms:
        mask &= haystack.str.contains(term, regex=False)
    results = df[mask].head(top_k)
    return results.fillna("").to_dict(orient="records")
