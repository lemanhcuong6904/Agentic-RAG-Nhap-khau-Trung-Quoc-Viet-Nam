from __future__ import annotations

import re

import pandas as pd

from agentic_rag_import_vn.config import settings
from agentic_rag_import_vn.io_utils import read_table
from agentic_rag_import_vn.processing.vnaccs import query_terms
from agentic_rag_import_vn.quality.text import normalized_key


CODE_TYPE_KEYWORDS = {
    "currency": {"tien te", "currency", "ngoai te"},
    "unit": {"don vi tinh", "dvt", "unit"},
    "airport": {"san bay", "airport"},
    "seaport": {"cang", "port", "icd"},
    "country": {"nuoc", "quoc gia", "country"},
}


class VnaccsRepository:
    def __init__(self) -> None:
        self.path = settings.curated_dir / "vnaccs" / "vnaccs_codes.parquet"

    def load(self) -> pd.DataFrame:
        return read_table(self.path)

    def infer_code_type(self, query: str, code_group: str | None = None) -> str | None:
        text = normalized_key(f"{query} {code_group or ''}")
        for code_type, keywords in CODE_TYPE_KEYWORDS.items():
            if any(keyword in text for keyword in keywords):
                return code_type
        return None

    def filter_code_type(self, df: pd.DataFrame, code_type: str | None) -> pd.DataFrame:
        if not code_type:
            return df
        group = df["code_group"].fillna("").map(normalized_key)
        title = df["source_title"].fillna("").map(normalized_key)
        combined = group + " " + title
        keywords = CODE_TYPE_KEYWORDS.get(code_type, set())
        if not keywords:
            return df
        mask = combined.apply(lambda value: any(keyword in value for keyword in keywords))
        return df[mask].copy()

    def lookup(
        self,
        query: str,
        *,
        code_type: str | None = None,
        code_group: str | None = None,
        limit: int = 20,
    ) -> list[dict[str, object]]:
        df = self.load()
        if df.empty:
            return []
        code_type = code_type or self.infer_code_type(query, code_group)
        df = self.filter_code_type(df, code_type)
        if code_group:
            key = normalized_key(code_group)
            df = df[df["code_group"].fillna("").map(normalized_key).str.contains(key, regex=False)].copy()
        if df.empty:
            return []

        code_candidates = [token.lower() for token in re.findall(r"[A-Za-z0-9]{2,}", query) if token.isupper() or any(ch.isdigit() for ch in token)]
        exact = pd.Series([False] * len(df), index=df.index)
        for token in code_candidates:
            exact |= df["code"].fillna("").str.lower().eq(token)
        if exact.any():
            return df[exact].head(limit).fillna("").to_dict(orient="records")

        terms = query_terms(query)
        if not terms:
            return []
        haystack = df["search_text"].fillna("").str.lower()
        all_mask = pd.Series([True] * len(df), index=df.index)
        any_mask = pd.Series([False] * len(df), index=df.index)
        for term in terms:
            term_mask = haystack.str.contains(term, regex=False)
            all_mask &= term_mask
            any_mask |= term_mask
        results = pd.concat([df[all_mask], df[any_mask & ~all_mask]], ignore_index=True)
        return results.head(limit).fillna("").to_dict(orient="records")
