from __future__ import annotations

import hashlib
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from agentic_rag_import_vn.config import settings
from agentic_rag_import_vn.io_utils import ensure_dirs, write_table


SUPPORTED_EXTENSIONS = {
    ".csv",
    ".doc",
    ".docx",
    ".pdf",
    ".rar",
    ".txt",
    ".xls",
    ".xlsx",
    ".xml",
    ".zip",
}


@dataclass(frozen=True)
class InventoryOutputs:
    documents_path: Path
    registry_path: Path
    inventory_report_path: Path
    quality_report_path: Path


def sha256_file(path: Path, chunk_size: int = 1024 * 1024) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as file:
        for chunk in iter(lambda: file.read(chunk_size), b""):
            digest.update(chunk)
    return digest.hexdigest()


def category_from_path(path: Path, raw_dir: Path) -> str:
    try:
        rel = path.relative_to(raw_dir)
    except ValueError:
        return "unknown"
    return rel.parts[0] if rel.parts else "unknown"


def infer_agreement(path: Path) -> str | None:
    text = str(path).lower()
    if "acfta" in text or "trung quốc" in text or "trung quoc" in text or "form e" in text:
        return "ACFTA"
    if "rcep" in text:
        return "RCEP"
    if "mfn" in text:
        return "MFN"
    return None


def infer_domain_category(folder: str) -> str:
    lower = folder.lower()
    if "hs" in lower or "danh mục" in lower or "danh muc" in lower:
        return "hs"
    if "thuế" in lower or "thue" in lower or "mfn" in lower:
        return "tariff"
    if "origin" in lower or "xuất xứ" in lower or "xuat xu" in lower or "certificate" in lower:
        return "origin"
    if "vnaccs" in lower or "bảng mã" in lower or "bang ma" in lower:
        return "vnaccs"
    if "statistics" in lower or "thống kê" in lower or "thong ke" in lower:
        return "statistics"
    if "vat" in lower:
        return "vat"
    return "legal"


def scan_raw(raw_dir: Path | None = None) -> pd.DataFrame:
    raw_dir = raw_dir or settings.raw_dir
    rows: list[dict[str, object]] = []
    ingested_at = datetime.now(timezone.utc).isoformat()

    for path in sorted(raw_dir.rglob("*")):
        if not path.is_file():
            continue
        rel_path = path.relative_to(settings.project_root).as_posix()
        extension = path.suffix.lower()
        folder = category_from_path(path, raw_dir)
        stat = path.stat()
        digest = sha256_file(path)
        document_id = digest[:16]
        rows.append(
            {
                "document_id": document_id,
                "title": path.stem,
                "file_name": path.name,
                "relative_path": rel_path,
                "file_type": extension.lstrip("."),
                "category_folder": folder,
                "category": infer_domain_category(folder),
                "agreement": infer_agreement(path),
                "origin_country": "CN" if infer_agreement(path) in {"ACFTA", "RCEP"} else None,
                "language": "vi",
                "size_bytes": stat.st_size,
                "modified_time": datetime.fromtimestamp(stat.st_mtime, timezone.utc).isoformat(),
                "sha256": digest,
                "duplicate_of": None,
                "parser": parser_for_extension(extension),
                "parser_version": settings.parser_version,
                "status": "unknown",
                "source_url": None,
                "needs_review": extension not in SUPPORTED_EXTENSIONS,
                "ingested_at": ingested_at,
            }
        )

    df = pd.DataFrame(rows)
    if df.empty:
        return df

    canonical_by_hash: dict[str, str] = {}
    duplicate_of: list[str | None] = []
    for _, row in df.iterrows():
        digest = str(row["sha256"])
        if digest in canonical_by_hash:
            duplicate_of.append(canonical_by_hash[digest])
        else:
            canonical_by_hash[digest] = str(row["document_id"])
            duplicate_of.append(None)
    df["duplicate_of"] = duplicate_of
    return df


def parser_for_extension(extension: str) -> str:
    return {
        ".pdf": "pypdf",
        ".docx": "python-docx",
        ".doc": "legacy-doc-needs-conversion",
        ".xls": "pandas-xlrd",
        ".xlsx": "pandas-openpyxl",
        ".csv": "pandas-csv",
        ".zip": "archive-needs-extract",
        ".rar": "archive-needs-extract",
    }.get(extension, "unsupported")


def write_reports(df: pd.DataFrame) -> tuple[Path, Path]:
    ensure_dirs([settings.reports_dir])
    inventory_report = settings.reports_dir / "data_inventory.md"
    quality_report = settings.reports_dir / "data_quality_initial.md"

    if df.empty:
        inventory_report.write_text("# Data Inventory\n\nNo files found.\n", encoding="utf-8")
        quality_report.write_text("# Initial Data Quality\n\nNo files found.\n", encoding="utf-8")
        return inventory_report, quality_report

    by_category = Counter(df["category"])
    by_type = Counter(df["file_type"])
    duplicate_count = int(df["duplicate_of"].notna().sum())
    total_size = int(df["size_bytes"].sum())

    lines = [
        "# Data Inventory",
        "",
        f"- Total files: {len(df):,}",
        f"- Total size: {total_size / 1024 / 1024:.2f} MB",
        f"- Duplicate files by SHA256: {duplicate_count:,}",
        "",
        "## By Domain Category",
        "",
        "| Category | Files |",
        "|---|---:|",
    ]
    lines.extend(f"| {category} | {count:,} |" for category, count in sorted(by_category.items()))
    lines.extend(["", "## By File Type", "", "| Type | Files |", "|---|---:|"])
    lines.extend(f"| {file_type or '(none)'} | {count:,} |" for file_type, count in sorted(by_type.items()))
    inventory_report.write_text("\n".join(lines) + "\n", encoding="utf-8")

    parser_counts = Counter(df["parser"])
    unsupported = df[df["parser"].isin(["unsupported", "legacy-doc-needs-conversion", "archive-needs-extract"])]
    quality_lines = [
        "# Initial Data Quality",
        "",
        "## Parser Coverage",
        "",
        "| Parser | Files |",
        "|---|---:|",
    ]
    quality_lines.extend(f"| {parser} | {count:,} |" for parser, count in sorted(parser_counts.items()))
    quality_lines.extend(
        [
            "",
            "## Risks",
            "",
            f"- Files requiring conversion/extraction/review: {len(unsupported):,}",
            "- Document legal validity is stored as `unknown` until official effective dates are parsed.",
            "- Raw customs statistics PDFs are inventory-only in this MVP until table extraction is validated.",
            "",
            "## Top Review Candidates",
            "",
            "| File | Reason |",
            "|---|---|",
        ]
    )
    for _, row in unsupported.head(25).iterrows():
        quality_lines.append(f"| `{row['relative_path']}` | {row['parser']} |")
    quality_report.write_text("\n".join(quality_lines) + "\n", encoding="utf-8")
    return inventory_report, quality_report


def build_document_registry(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return df
    registry = df[
        [
            "document_id",
            "title",
            "file_name",
            "relative_path",
            "file_type",
            "category",
            "agreement",
            "origin_country",
            "language",
            "status",
            "sha256",
            "duplicate_of",
            "source_url",
            "ingested_at",
            "parser_version",
            "needs_review",
        ]
    ].copy()
    return registry


def run_inventory() -> InventoryOutputs:
    ensure_dirs([settings.manifests_dir, settings.processed_dir, settings.reports_dir])
    df = scan_raw()
    documents_path = write_table(df, settings.manifests_dir / "documents.parquet")
    registry = build_document_registry(df)
    registry_path = write_table(registry, settings.processed_dir / "document_registry.parquet")
    inventory_report, quality_report = write_reports(df)
    return InventoryOutputs(
        documents_path=documents_path,
        registry_path=registry_path,
        inventory_report_path=inventory_report,
        quality_report_path=quality_report,
    )


def duplicate_groups(df: pd.DataFrame) -> dict[str, list[str]]:
    groups: dict[str, list[str]] = defaultdict(list)
    if df.empty:
        return groups
    for _, row in df.iterrows():
        groups[str(row["sha256"])].append(str(row["relative_path"]))
    return {digest: paths for digest, paths in groups.items() if len(paths) > 1}
