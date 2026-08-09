from __future__ import annotations

from agentic_rag_import_vn.quality.text import normalized_key


PRODUCT_SYNONYMS: dict[str, list[str]] = {
    "ca rong": ["arowana", "arowanas", "scleropages formosus", "0301 11 95", "03011195"],
}


def expand_query(query: str) -> str:
    normalized = normalized_key(query)
    additions: list[str] = []
    for trigger, synonyms in PRODUCT_SYNONYMS.items():
        if trigger in normalized:
            additions.extend(synonyms)
    if not additions:
        return query
    return f"{query} {' '.join(dict.fromkeys(additions))}"
