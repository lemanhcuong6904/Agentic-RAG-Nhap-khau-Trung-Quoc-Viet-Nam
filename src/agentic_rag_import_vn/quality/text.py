from __future__ import annotations

import re
import unicodedata


def strip_accents(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", str(value))
    return "".join(ch for ch in normalized if not unicodedata.combining(ch))


def normalized_key(value: str) -> str:
    value = strip_accents(value).lower()
    value = re.sub(r"[^a-z0-9]+", " ", value)
    return re.sub(r"\s+", " ", value).strip()


def text_quality(text: str) -> dict[str, object]:
    text = str(text or "")
    length = len(text)
    replacement_count = text.count("\ufffd")
    control_count = sum(1 for ch in text if unicodedata.category(ch).startswith("C") and ch not in "\n\r\t")
    printable_count = sum(1 for ch in text if ch.isprintable() or ch in "\n\r\t")
    words = re.findall(r"\w+", text, flags=re.UNICODE)
    numeric_tokens = re.findall(r"\d+(?:[.,]\d+)*%?", text)
    hs_like = re.findall(r"\b\d{4}(?:[.\s-]?\d{2}){1,2}\b", text)
    replacement_ratio = replacement_count / max(length, 1)
    control_ratio = control_count / max(length, 1)
    printable_ratio = printable_count / max(length, 1)
    status = "pass"
    needs_review = False
    reasons: list[str] = []
    if length < 40:
        status = "review"
        needs_review = True
        reasons.append("very_short_text")
    if replacement_ratio > 0.01:
        status = "review"
        needs_review = True
        reasons.append("unicode_replacement_ratio_high")
    if control_ratio > 0.01 or printable_ratio < 0.95:
        status = "review"
        needs_review = True
        reasons.append("non_printable_ratio_high")
    return {
        "char_count": length,
        "word_count": len(words),
        "line_count": len([line for line in text.splitlines() if line.strip()]),
        "replacement_ratio": replacement_ratio,
        "control_ratio": control_ratio,
        "printable_ratio": printable_ratio,
        "numeric_token_count": len(numeric_tokens),
        "hs_like_count": len(hs_like),
        "status": status,
        "needs_review": needs_review,
        "reasons": reasons,
    }
