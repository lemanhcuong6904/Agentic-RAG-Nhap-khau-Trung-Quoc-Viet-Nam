from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date

from agentic_rag_import_vn.processing.vnaccs import search_vnaccs
from agentic_rag_import_vn.retrieval.bm25 import search as legal_search


HS_RE = re.compile(r"\b\d{4}(?:\.?\d{2}){0,2}\b")


@dataclass(frozen=True)
class AgentResponse:
    answer: str
    intent: str
    confidence: str
    warnings: list[str]
    sources: list[dict[str, object]]
    tool_calls: list[dict[str, object]]


def classify_intent(query: str) -> str:
    lower = query.lower()
    if any(term in lower for term in ["vnaccs", "mã cảng", "ma cang", "cny", "tiền tệ", "tien te", "đơn vị tính"]):
        return "vnaccs"
    if any(term in lower for term in ["c/o", "co form", "form e", "xuất xứ", "xuat xu", "rcep", "acfta"]):
        return "origin"
    if any(term in lower for term in ["thuế", "thue", "mfn", "vat"]):
        return "tariff"
    if "hs" in lower or HS_RE.search(query):
        return "hs"
    return "legal"


def answer_query(query: str, query_date: date | None = None) -> AgentResponse:
    query_date = query_date or date.today()
    intent = classify_intent(query)
    warnings = [
        "MVP chỉ tư vấn theo dữ liệu đã ingest; trạng thái hiệu lực văn bản mặc định là unknown nếu chưa parse được metadata pháp lý.",
    ]
    tool_calls: list[dict[str, object]] = []
    sources: list[dict[str, object]] = []

    if intent == "vnaccs":
        rows = search_vnaccs(query, top_k=8)
        tool_calls.append({"tool": "vnaccs.search", "args": {"query": query, "top_k": 8}, "rows": len(rows)})
        sources = [
            {
                "document_id": row.get("source_document_id"),
                "title": row.get("source_title"),
                "path": row.get("source_path"),
            }
            for row in rows
        ]
        if rows:
            lines = ["Kết quả tra cứu VNACCS:"]
            for row in rows[:8]:
                lines.append(f"- `{row.get('code')}`: {row.get('description') or row.get('code_group')}")
            return AgentResponse("\n".join(lines), intent, "medium", warnings, sources, tool_calls)
        return AgentResponse(
            "Chưa tìm thấy mã VNACCS phù hợp trong bảng đã xử lý. Hãy chạy lại `build-vnaccs` trong env có đủ `xlrd/openpyxl` hoặc nhập từ khóa cụ thể hơn.",
            intent,
            "low",
            warnings,
            sources,
            tool_calls,
        )

    results = legal_search(query, top_k=5)
    tool_calls.append({"tool": "legal.search", "args": {"query": query, "top_k": 5}, "rows": len(results)})
    sources = [
        {
            "document_id": row.get("document_id"),
            "title": row.get("title"),
            "path": row.get("relative_path"),
            "page": row.get("page"),
            "score": row.get("score"),
        }
        for row in results
    ]

    if not results:
        return AgentResponse(
            "Chưa có evidence phù hợp trong index hiện tại. Hãy chạy `extract-text`, `build-chunks`, `build-bm25` trên toàn bộ dữ liệu trước khi dùng câu hỏi này.",
            intent,
            "low",
            warnings,
            sources,
            tool_calls,
        )

    lines = [
        f"Ngày tra cứu: {query_date.isoformat()}",
        "Các đoạn nguồn liên quan nhất:",
    ]
    for index, row in enumerate(results, start=1):
        page = f", trang {row.get('page')}" if row.get("page") else ""
        lines.append(f"{index}. {row.get('title')}{page}: {str(row.get('text'))[:450]}")

    if intent in {"hs", "tariff"}:
        warnings.append("Không kết luận mã HS hoặc thuế suất nếu chưa có bảng HS/tariff có cấu trúc được parse và filter theo ngày.")
    if intent in {"origin", "tariff"}:
        warnings.append("Thuế FTA chỉ là khả năng áp dụng; cần kiểm tra quy tắc xuất xứ và C/O hợp lệ.")

    return AgentResponse("\n".join(lines), intent, "medium", warnings, sources, tool_calls)
