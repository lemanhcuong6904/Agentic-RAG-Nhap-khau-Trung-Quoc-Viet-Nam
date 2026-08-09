from agentic_rag_import_vn.agents.orchestrator import classify_intent


def test_classify_vnaccs_intent() -> None:
    assert classify_intent("Tra mã tiền tệ CNY") == "vnaccs"


def test_classify_origin_intent() -> None:
    assert classify_intent("C/O Form E theo ACFTA cần gì?") == "origin"


def test_classify_tariff_intent() -> None:
    assert classify_intent("HS 850940 thuế MFN bao nhiêu?") == "tariff"
