from __future__ import annotations

import re
from pathlib import Path

import pandas as pd
from tqdm import tqdm

from agentic_rag_import_vn.config import settings
from agentic_rag_import_vn.io_utils import ensure_dirs, read_table, write_table
from agentic_rag_import_vn.quality.audit import finish_run, new_run, write_events, write_processing_run
from agentic_rag_import_vn.quality.text import normalized_key


VNACCS_EXTENSIONS = {"xlsx", "xls", "csv"}


def compact_row(values: list[object]) -> tuple[str | None, str]:
    cleaned = [str(value).strip() for value in values if pd.notna(value) and str(value).strip()]
    if not cleaned:
        return None, ""
    code = cleaned[0]
    description = " | ".join(cleaned[1:]) if len(cleaned) > 1 else ""
    return code, description


def looks_like_header_or_noise(code: str) -> bool:
    key = normalized_key(code)
    return key in {"stt", "ma", "code", "ky hieu"} or key.startswith("danh sach")


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
            if not code or looks_like_header_or_noise(code):
                continue
            rows.append(
                {
                    "sheet": str(sheet_name),
                    "row_number": int(row_index) + 1,
                    "code": code,
                    "description": description,
                    "search_text": f"{code} {description}".strip(),
                    "quality_status": "pass" if code.strip() else "review",
                }
            )
    return rows


def run_vnaccs_build() -> Path:
    run = new_run("build_vnaccs")
    ensure_dirs([settings.processed_dir / "vnaccs_codes", settings.curated_dir / "vnaccs", settings.manifests_dir])
    registry = read_table(settings.processed_dir / "document_registry.parquet")
    candidates = registry[
        (registry["document_role"] == "vnaccs_dictionary")
        & registry["file_type"].isin(VNACCS_EXTENSIONS)
        & registry["duplicate_of"].isna()
    ].copy()
    candidates = candidates[~candidates["file_name"].str.lower().isin({"metadata.csv"})].copy()

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
                    "source_sha256": doc.get("sha256"),
                    "code_group": doc["title"],
                    "status": doc.get("status", "unknown"),
                    "parser_version": settings.parser_version,
                    "provenance_quality": "pass",
                }
            )
            all_rows.append(row)

    if errors:
        write_table(pd.DataFrame(errors), settings.manifests_dir / "vnaccs_errors.csv")
    else:
        stale_errors = settings.manifests_dir / "vnaccs_errors.csv"
        if stale_errors.exists():
            stale_errors.unlink()

    df = pd.DataFrame(all_rows)
    processed = write_table(df, settings.processed_dir / "vnaccs_codes" / "vnaccs_codes.parquet")
    curated = df[df["quality_status"] == "pass"].copy() if not df.empty else df
    write_table(curated, settings.curated_dir / "vnaccs" / "vnaccs_codes.parquet")
    write_processing_run(
        finish_run(run, metrics={"documents_attempted": len(candidates), "rows": len(df), "errors": len(errors)})
    )
    write_events(
        [
            {
                "run_id": run["run_id"],
                "stage": "build_vnaccs",
                "event_type": "artifact_written",
                "artifact": str(processed),
            }
        ]
    )
    return processed


def query_terms(query: str) -> list[str]:
    stopwords = {
        "tra",
        "tim",
        "tìm",
        "ma",
        "mã",
        "vnaccs",
        "la",
        "là",
        "gi",
        "gì",
        "cho",
        "toi",
        "tôi",
        "cua",
        "của",
    }
    terms = normalized_key(query).split()
    return [term for term in terms if term not in stopwords and len(term) > 1]


def code_terms(query: str) -> list[str]:
    tokens = re.findall(r"[A-Za-z0-9]{2,}", query)
    return [token.lower() for token in tokens if token.isupper() or any(ch.isdigit() for ch in token)]


def search_vnaccs(query: str, top_k: int = 20) -> list[dict[str, object]]:
    path = settings.curated_dir / "vnaccs" / "vnaccs_codes.parquet"
    if not path.exists():
        path = settings.processed_dir / "vnaccs_codes" / "vnaccs_codes.parquet"
    df = read_table(path)
    if df.empty:
        return []
    terms = query_terms(query)
    if not terms:
        return []
    haystack = df["search_text"].fillna("").str.lower()
    exact_code = pd.Series([False] * len(df))
    for term in code_terms(query):
        exact_code |= df["code"].fillna("").str.lower().eq(term)
    if exact_code.any():
        results = df[exact_code].head(top_k)
        return results.fillna("").to_dict(orient="records")

    any_mask = pd.Series([False] * len(df))
    all_mask = pd.Series([True] * len(df))
    for term in terms:
        term_mask = haystack.str.contains(term, regex=False)
        any_mask |= term_mask
        all_mask &= term_mask
    strict_results = df[all_mask]
    fallback_results = df[any_mask & ~all_mask]
    results = pd.concat([strict_results, fallback_results], ignore_index=True).head(top_k)
    return results.fillna("").to_dict(orient="records")
