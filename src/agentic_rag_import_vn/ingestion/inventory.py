from __future__ import annotations

import hashlib
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from agentic_rag_import_vn.config import settings
from agentic_rag_import_vn.io_utils import ensure_dirs, write_table
from agentic_rag_import_vn.quality.audit import finish_run, new_run, write_events, write_processing_run
from agentic_rag_import_vn.quality.routing import parser_for_strategy, route_document
from agentic_rag_import_vn.quality.text import normalized_key


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
    text = normalized_key(str(path))
    if "rcep" in text:
        return "RCEP"
    if "acfta" in text or "asean china" in text or "trung quoc" in text or "form e" in text:
        return "ACFTA"
    if "mfn" in text:
        return "MFN"
    return None


def infer_domain_category(folder: str) -> str:
    lower = normalized_key(folder)
    if "hs" in lower or "danh muc" in lower:
        return "hs"
    if "thue" in lower or "mfn" in lower:
        return "tariff"
    if "origin" in lower or "xuat xu" in lower or "certificate" in lower or lower == "co":
        return "origin"
    if "vnaccs" in lower or "bang ma" in lower:
        return "vnaccs"
    if "statistics" in lower or "thong ke" in lower:
        return "statistics"
    if "vat" in lower:
        return "vat"
    return "legal"


def metadata_quality_status(row: pd.Series) -> str:
    required = ["document_id", "sha256", "file_name", "relative_path", "category", "document_role", "parse_strategy"]
    if any(pd.isna(row.get(field)) or row.get(field) in {"", None} for field in required):
        return "fail"
    if row.get("duplicate_of"):
        return "review"
    if row.get("risk_level") == "high" and row.get("status") == "unknown":
        return "review"
    return "pass"


def scan_raw(raw_dir: Path | None = None) -> pd.DataFrame:
    raw_dir = raw_dir or settings.raw_dir
    rows: list[dict[str, object]] = []
    ingested_at = datetime.now(timezone.utc).isoformat()

    for path in sorted(raw_dir.rglob("*")):
        if not path.is_file():
            continue
        rel_path = path.relative_to(settings.project_root).as_posix()
        extension = path.suffix.lower()
        file_type = extension.lstrip(".")
        folder = category_from_path(path, raw_dir)
        category = infer_domain_category(folder)
        route = route_document(rel_path, category, file_type)
        agreement = infer_agreement(path)
        stat = path.stat()
        digest = sha256_file(path)
        document_id = digest[:16]
        rows.append(
            {
                "document_id": document_id,
                "sha256": digest,
                "title": path.stem,
                "file_name": path.name,
                "relative_path": rel_path,
                "extension": extension,
                "file_type": file_type,
                "file_size": stat.st_size,
                "category_folder": folder,
                "category": category,
                "document_role": route.document_role,
                "agreement": agreement,
                "applicable_country": "CN" if agreement in {"ACFTA", "RCEP"} else None,
                "origin_country": "CN" if agreement in {"ACFTA", "RCEP"} else None,
                "language": "vi",
                "size_bytes": stat.st_size,
                "modified_time": datetime.fromtimestamp(stat.st_mtime, timezone.utc).isoformat(),
                "duplicate_of": None,
                "parse_strategy": route.parse_strategy,
                "expected_outputs": route.expected_outputs,
                "risk_level": route.risk_level,
                "parser": parser_for_strategy(route.parse_strategy, file_type),
                "parser_version": settings.parser_version,
                "status": "unknown",
                "document_number": None,
                "issuing_authority": None,
                "promulgation_date": None,
                "effective_from": None,
                "effective_to": None,
                "source_url": None,
                "source_page": None,
                "download_url": None,
                "needs_ocr": None,
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
    df["is_canonical"] = df["duplicate_of"].isna()
    df["metadata_quality"] = df.apply(metadata_quality_status, axis=1)
    df["provenance_quality"] = df.apply(
        lambda row: "partial" if not row.get("source_url") and not row.get("download_url") else "pass",
        axis=1,
    )
    df["temporal_quality"] = "unknown"
    return df


def parser_for_extension(extension: str) -> str:
    return parser_for_strategy(route_document("", "legal", extension.lstrip(".")).parse_strategy, extension.lstrip("."))


def build_document_registry(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return df
    columns = [
        "document_id",
        "sha256",
        "title",
        "file_name",
        "relative_path",
        "extension",
        "file_type",
        "file_size",
        "category",
        "document_role",
        "agreement",
        "applicable_country",
        "origin_country",
        "language",
        "document_number",
        "issuing_authority",
        "promulgation_date",
        "effective_from",
        "effective_to",
        "status",
        "duplicate_of",
        "is_canonical",
        "source_url",
        "source_page",
        "download_url",
        "parse_strategy",
        "expected_outputs",
        "risk_level",
        "parser",
        "needs_ocr",
        "ingested_at",
        "parser_version",
        "needs_review",
        "metadata_quality",
        "provenance_quality",
        "temporal_quality",
    ]
    return df[columns].copy()


def build_duplicates(df: pd.DataFrame) -> pd.DataFrame:
    columns = ["document_id", "duplicate_of", "sha256", "relative_path", "file_name", "category"]
    if df.empty:
        return pd.DataFrame(columns=columns)
    duplicate_rows = df[df["duplicate_of"].notna()].copy()
    if duplicate_rows.empty:
        return pd.DataFrame(columns=columns)
    return duplicate_rows[columns]


def build_review_queue(df: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    for _, row in df.iterrows():
        reasons: list[str] = []
        if row.get("duplicate_of"):
            reasons.append("duplicate_document")
        if row.get("parser") in {"legacy-doc-needs-conversion", "archive-needs-extract", "unsupported"}:
            reasons.append(str(row.get("parser")))
        if row.get("risk_level") == "high":
            reasons.append("high_risk_requires_structured_validation")
        if row.get("provenance_quality") == "partial":
            reasons.append("missing_official_source_url")
        if reasons:
            rows.append(
                {
                    "review_id": f"review-{row['document_id']}",
                    "document_id": row["document_id"],
                    "relative_path": row["relative_path"],
                    "severity": "high" if row.get("risk_level") == "high" else "medium",
                    "stage": "inventory",
                    "reasons": reasons,
                    "status": "open",
                    "created_at": datetime.now(timezone.utc).isoformat(),
                }
            )
    return pd.DataFrame(rows)


def write_reports(df: pd.DataFrame) -> tuple[Path, Path]:
    ensure_dirs([settings.reports_dir])
    inventory_report = settings.reports_dir / "data_inventory.md"
    quality_report = settings.reports_dir / "data_quality_initial.md"

    if df.empty:
        inventory_report.write_text("# Data Inventory\n\nNo files found.\n", encoding="utf-8")
        quality_report.write_text("# Initial Data Quality\n\nNo files found.\n", encoding="utf-8")
        return inventory_report, quality_report

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
    lines.extend(f"| {category} | {count:,} |" for category, count in sorted(Counter(df["category"]).items()))
    lines.extend(["", "## By Document Role", "", "| Role | Files |", "|---|---:|"])
    lines.extend(f"| {role} | {count:,} |" for role, count in sorted(Counter(df["document_role"]).items()))
    lines.extend(["", "## By Risk Level", "", "| Risk | Files |", "|---|---:|"])
    lines.extend(f"| {risk} | {count:,} |" for risk, count in sorted(Counter(df["risk_level"]).items()))
    lines.extend(["", "## By File Type", "", "| Type | Files |", "|---|---:|"])
    lines.extend(f"| {file_type or '(none)'} | {count:,} |" for file_type, count in sorted(Counter(df["file_type"]).items()))
    inventory_report.write_text("\n".join(lines) + "\n", encoding="utf-8")

    parser_counts = Counter(df["parser"])
    review = build_review_queue(df)
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
            "## Quality Gate Summary",
            "",
            f"- High-risk documents requiring structured validation before curated promotion: {int((df['risk_level'] == 'high').sum()):,}",
            f"- Documents with partial provenance metadata: {int((df['provenance_quality'] == 'partial').sum()):,}",
            f"- Open review queue items: {len(review):,}",
            "- Legal validity remains `unknown` until temporal metadata is parsed or curated.",
            "- Indexes must be built from `data/curated`, not raw `processed` data.",
            "",
            "## Top Review Candidates",
            "",
            "| File | Reason |",
            "|---|---|",
        ]
    )
    for _, row in review.head(30).iterrows():
        quality_lines.append(f"| `{row['relative_path']}` | {', '.join(row['reasons'])} |")
    quality_report.write_text("\n".join(quality_lines) + "\n", encoding="utf-8")
    return inventory_report, quality_report


def run_inventory() -> InventoryOutputs:
    run = new_run("inventory")
    ensure_dirs([settings.manifests_dir, settings.processed_dir, settings.reports_dir])
    df = scan_raw()
    documents_path = write_table(df, settings.manifests_dir / "documents.parquet")
    registry = build_document_registry(df)
    registry_path = write_table(registry, settings.processed_dir / "document_registry.parquet")
    duplicates = build_duplicates(df)
    review = build_review_queue(df)
    write_table(duplicates, settings.manifests_dir / "duplicates.parquet")
    write_table(review, settings.manifests_dir / "review_queue.parquet")
    inventory_report, quality_report = write_reports(df)
    write_processing_run(
        finish_run(
            run,
            metrics={"documents": len(df), "duplicates": len(duplicates), "review_items": len(review)},
        )
    )
    write_events(
        [
            {
                "run_id": run["run_id"],
                "stage": "inventory",
                "event_type": "artifact_written",
                "artifact": str(documents_path),
                "created_at": datetime.now(timezone.utc).isoformat(),
            }
        ]
    )
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
