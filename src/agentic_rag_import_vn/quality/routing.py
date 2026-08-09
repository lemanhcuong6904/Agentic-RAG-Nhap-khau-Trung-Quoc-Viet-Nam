from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from agentic_rag_import_vn.quality.text import normalized_key


@dataclass(frozen=True)
class Route:
    document_role: str
    parse_strategy: str
    expected_outputs: list[str]
    risk_level: str


def route_document(relative_path: str, category: str, file_type: str) -> Route:
    key = normalized_key(relative_path)
    suffix = file_type.lower().lstrip(".")
    is_table_file = suffix in {"xls", "xlsx", "csv"}

    if category == "vnaccs":
        return Route("vnaccs_dictionary", "spreadsheet_table" if is_table_file else "legacy_or_text", ["tables"], "high")
    if category == "statistics":
        return Route("statistics_report", "pdf_table" if suffix == "pdf" else "spreadsheet_table", ["tables", "metadata"], "high")
    if category == "hs":
        return Route("hs_master", "structured_table" if is_table_file else "pdf_table", ["tables", "text"], "high")
    if category == "tariff":
        return Route("tariff_table", "structured_table" if is_table_file else "pdf_table", ["tables", "text"], "high")
    if "psr" in key or "quy tac cu the" in key or "phu luc i" in key:
        return Route("origin_psr", "pdf_table" if suffix == "pdf" else "docx_table", ["tables", "text"], "high")
    if category == "origin":
        return Route("origin_legal", "legal_narrative", ["text", "markdown"], "medium")
    if category == "vat":
        return Route("vat_legal", "legal_narrative", ["text", "markdown"], "medium")
    return Route("legal_general", "legal_narrative", ["text", "markdown"], "low")


def parser_for_strategy(parse_strategy: str, file_type: str) -> str:
    suffix = file_type.lower().lstrip(".")
    if parse_strategy in {"spreadsheet_table", "structured_table"}:
        return "pandas-openpyxl" if suffix == "xlsx" else "pandas-xlrd" if suffix == "xls" else "pandas-csv"
    if suffix == "pdf":
        return "pypdf-layout"
    if suffix == "docx":
        return "python-docx-structured"
    if suffix == "doc":
        return "legacy-doc-needs-conversion"
    if suffix in {"zip", "rar"}:
        return "archive-needs-extract"
    return "unsupported"
