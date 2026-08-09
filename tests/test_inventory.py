from pathlib import Path

from agentic_rag_import_vn.ingestion.inventory import infer_agreement, infer_domain_category, parser_for_extension
from agentic_rag_import_vn.quality.routing import route_document


def test_infer_domain_category() -> None:
    assert infer_domain_category("Các bảng mã VNACCS") == "vnaccs"
    assert infer_domain_category("Thuế nhập khẩu MFN") == "tariff"


def test_parser_for_extension() -> None:
    assert parser_for_extension(".pdf") == "pypdf-layout"
    assert parser_for_extension(".rar") == "archive-needs-extract"


def test_rcep_not_inferred_as_acfta() -> None:
    assert infer_agreement(Path("data/raw/Thuế RCEP/Việt Nam cho Trung Quốc.pdf")) == "RCEP"


def test_route_tariff_as_high_risk_table() -> None:
    route = route_document("data/raw/Thuế RCEP/129-1.pdf", "tariff", "pdf")
    assert route.document_role == "tariff_table"
    assert route.risk_level == "high"
