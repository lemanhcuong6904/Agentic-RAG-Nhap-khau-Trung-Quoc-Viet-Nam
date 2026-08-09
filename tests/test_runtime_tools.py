from agentic_rag_import_vn.agents.orchestrator import answer_query, understand_intents
from agentic_rag_import_vn.repositories.vnaccs import VnaccsRepository
from agentic_rag_import_vn.tools.legal import search_legal_documents
from agentic_rag_import_vn.tools.vnaccs import lookup_vnaccs


def test_understand_vnaccs_currency_intent() -> None:
    assert "vnaccs_lookup" in understand_intents("Tra mã tiền tệ CNY")


def test_vnaccs_currency_filter_prefers_currency_rows() -> None:
    rows = VnaccsRepository().lookup("CNY", code_type="currency", limit=5)
    assert rows
    assert all(row["code"] == "CNY" for row in rows)
    assert any("Nhân dân tệ" in row["description"] for row in rows)


def test_vnaccs_tool_result_schema() -> None:
    result = lookup_vnaccs("CNY", code_type="currency", limit=5)
    assert result.status in {"success", "ambiguous"}
    assert result.data
    assert result.evidence


def test_legal_tool_returns_evidence() -> None:
    result = search_legal_documents("C/O Form E", agreement="ACFTA", top_k=3)
    assert result.status == "success"
    assert result.evidence


def test_agent_graph_warns_for_unavailable_hs() -> None:
    response = answer_query("Máy xay cà phê điện có mã HS nào?")
    assert response.tool_calls
    assert any("HS structured tool is not available" in warning for warning in response.warnings)


def test_product_synonym_finds_arowana_hs_evidence() -> None:
    result = search_legal_documents("Mã hàng cho hàng hóa cá rồng là gì?", top_k=5)
    evidence_text = " ".join(item.text or "" for item in result.evidence)
    assert result.status == "success"
    assert "0301 11 95" in evidence_text
    assert "Arowanas" in evidence_text
