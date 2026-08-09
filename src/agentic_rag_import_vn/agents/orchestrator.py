from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date
from uuid import uuid4

from agentic_rag_import_vn.config import settings
from agentic_rag_import_vn.quality.text import normalized_key
from agentic_rag_import_vn.schemas import Evidence, ImportAdvisoryState, ToolCallTrace, VerificationResult
from agentic_rag_import_vn.tools.legal import search_legal_documents
from agentic_rag_import_vn.tools.vnaccs import lookup_vnaccs


HS_RE = re.compile(r"\b\d{4}(?:\.?\d{2}){0,2}\b")


@dataclass(frozen=True)
class AgentResponse:
    answer: str
    intent: str
    confidence: str
    warnings: list[str]
    sources: list[dict[str, object]]
    tool_calls: list[dict[str, object]]
    state: dict[str, object] | None = None


def classify_intent(query: str) -> str:
    intents = understand_intents(query)
    if "vnaccs_lookup" in intents:
        return "vnaccs"
    if "origin_guidance" in intents:
        return "origin"
    if "tariff_lookup" in intents:
        return "tariff"
    if "hs_classification" in intents:
        return "hs"
    return "legal"


def understand_intents(query: str) -> list[str]:
    text = normalized_key(query)
    intents: list[str] = []
    if any(term in text for term in ["vnaccs", "ma cang", "cang", "san bay", "tien te", "don vi tinh", "dvt"]):
        intents.append("vnaccs_lookup")
    if any(term in text for term in ["c o", "form e", "co form", "xuat xu", "rcep", "acfta"]):
        intents.append("origin_guidance")
    if any(term in text for term in ["thue", "mfn", "vat"]):
        intents.append("tariff_lookup")
    if "hs" in text or HS_RE.search(query):
        intents.append("hs_classification")
    if not intents or any(term in text for term in ["quy dinh", "huong dan", "dieu", "nghi dinh", "thong tu"]):
        intents.append("legal_qa")
    return list(dict.fromkeys(intents))


def detect_unavailable_capabilities(intents: list[str]) -> list[str]:
    warnings: list[str] = []
    if "hs_classification" in intents and not settings.enable_hs:
        warnings.append("HS structured tool is not available yet; the agent will not assert a final HS code.")
    if "tariff_lookup" in intents and not settings.enable_tariff:
        warnings.append("Tariff structured tool is not available yet; the agent will not assert MFN/ACFTA/RCEP rates.")
    if "origin_guidance" in intents and not settings.enable_origin_psr:
        warnings.append("Origin PSR structured tool is not available yet; only general legal/C/O evidence can be searched.")
    return warnings


def plan_steps(intents: list[str]) -> list[dict[str, object]]:
    plan: list[dict[str, object]] = []
    if "vnaccs_lookup" in intents and settings.enable_vnaccs:
        plan.append({"id": "vnaccs", "tool": "lookup_vnaccs", "depends_on": []})
    if any(intent in intents for intent in ["legal_qa", "origin_guidance", "tariff_lookup", "hs_classification"]) and settings.enable_legal:
        plan.append({"id": "legal", "tool": "search_legal_documents", "depends_on": []})
    return plan


def execute_plan(state: ImportAdvisoryState) -> ImportAdvisoryState:
    for step in state.plan:
        tool = step["tool"]
        if tool == "lookup_vnaccs":
            result = lookup_vnaccs(state.query, limit=8)
            state.vnaccs_results = result.data
        elif tool == "search_legal_documents":
            agreement = None
            text = normalized_key(state.query)
            if "rcep" in text:
                agreement = "RCEP"
            elif "acfta" in text or "form e" in text:
                agreement = "ACFTA"
            result = search_legal_documents(state.query, agreement=agreement, top_k=8)
            state.legal_evidence = result.data
        else:
            continue
        state.evidence_pool.extend(result.evidence)
        state.warnings.extend(result.warnings)
        state.tool_trace.append(
            ToolCallTrace(
                tool=tool,
                args={"query": state.query},
                status=result.status,
                rows=len(result.data),
                warnings=result.warnings,
            )
        )
    return state


def verify_state(state: ImportAdvisoryState) -> ImportAdvisoryState:
    warnings = list(state.warnings)
    unsupported: list[str] = []
    if settings.require_evidence and not state.evidence_pool:
        unsupported.append("No evidence was retrieved from enabled tools.")
    if any(intent in state.intents for intent in ["hs_classification", "tariff_lookup"]):
        warnings.append("Numeric HS/tariff claims are blocked until curated structured tools are enabled.")
    if any(e.temporal_quality == "unknown" for e in state.evidence_pool):
        warnings.append("Some evidence has unknown temporal/effectivity metadata.")
    status = "fail" if unsupported else "warning" if warnings else "pass"
    state.verification = VerificationResult(status=status, warnings=list(dict.fromkeys(warnings)), unsupported_claims=unsupported)
    state.warnings = state.verification.warnings
    return state


def synthesize_answer(state: ImportAdvisoryState) -> ImportAdvisoryState:
    lines: list[str] = []
    if state.verification and state.verification.unsupported_claims:
        lines.append("Chưa đủ bằng chứng từ các tool đang bật để trả lời chắc chắn.")
    if state.vnaccs_results:
        lines.append("Kết quả tra cứu VNACCS:")
        for row in state.vnaccs_results[:8]:
            group = row.get("code_group") or row.get("source_title") or ""
            lines.append(f"- `{row.get('code')}`: {row.get('description') or group} ({group})")
    if state.legal_evidence:
        lines.append("Nguồn pháp lý liên quan:")
        for idx, hit in enumerate(state.legal_evidence[:5], start=1):
            page = f", trang {hit.get('page')}" if hit.get("page") else ""
            lines.append(f"{idx}. {hit.get('title')}{page}: {str(hit.get('text'))[:420]}")
    if not lines:
        lines.append("Chưa tìm thấy dữ liệu phù hợp trong các capability đang bật.")
    if state.warnings:
        lines.append("")
        lines.append("Cảnh báo/phạm vi:")
        for warning in list(dict.fromkeys(state.warnings)):
            lines.append(f"- {warning}")
    state.final_answer = "\n".join(lines)
    return state


def run_graph(query: str, query_date: date | None = None, session_id: str | None = None) -> ImportAdvisoryState:
    state = ImportAdvisoryState(
        request_id=str(uuid4()),
        session_id=session_id,
        query=query,
        query_date=query_date or date.today(),
    )
    state.intents = understand_intents(query)
    state.requested_tasks = state.intents
    state.warnings.extend(detect_unavailable_capabilities(state.intents))
    state.plan = plan_steps(state.intents)
    state = execute_plan(state)
    state = verify_state(state)
    state = synthesize_answer(state)
    return state


def answer_query(query: str, query_date: date | None = None) -> AgentResponse:
    state = run_graph(query, query_date=query_date)
    sources = [
        {
            "document_id": evidence.document_id,
            "title": evidence.title,
            "path": evidence.path,
            "page": evidence.page,
            "score": evidence.score,
            "source": evidence.source,
        }
        for evidence in state.evidence_pool
    ]
    confidence = "low" if state.verification and state.verification.status == "fail" else "medium"
    return AgentResponse(
        answer=state.final_answer or "",
        intent=classify_intent(query),
        confidence=confidence,
        warnings=state.warnings,
        sources=sources,
        tool_calls=[trace.model_dump() for trace in state.tool_trace],
        state=state.model_dump(mode="json"),
    )
