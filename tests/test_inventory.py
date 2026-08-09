from agentic_rag_import_vn.ingestion.inventory import infer_domain_category, parser_for_extension


def test_infer_domain_category() -> None:
    assert infer_domain_category("Các bảng mã VNACCS") == "vnaccs"
    assert infer_domain_category("Thuế nhập khẩu MFN") == "tariff"


def test_parser_for_extension() -> None:
    assert parser_for_extension(".pdf") == "pypdf"
    assert parser_for_extension(".rar") == "archive-needs-extract"
