from __future__ import annotations

from agentic_rag_import_vn.schemas import ImportAdvisoryState


def synthesis_prompt(state: ImportAdvisoryState) -> str:
    evidence_lines = []
    for idx, evidence in enumerate(state.evidence_pool[:8], start=1):
        citation = f"{evidence.title or evidence.document_id}"
        if evidence.page:
            citation += f", trang {evidence.page}"
        evidence_lines.append(f"[{idx}] {citation}\n{(evidence.text or '')[:900]}")
    warnings = "\n".join(f"- {warning}" for warning in state.warnings)
    return f"""Bạn là trợ lý tư vấn nhập khẩu Trung Quốc vào Việt Nam.
Chỉ dùng bằng chứng được cung cấp. Không tự tạo mã HS, thuế suất, PSR hoặc số liệu nếu tool chưa cung cấp.
Nếu metadata hiệu lực/provenance còn thiếu, phải cảnh báo.

Câu hỏi:
{state.query}

Bằng chứng:
{chr(10).join(evidence_lines)}

Cảnh báo bắt buộc:
{warnings}

Hãy trả lời ngắn gọn bằng tiếng Việt, có mục Nguồn và Cảnh báo nếu có.
"""
