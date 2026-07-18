from __future__ import annotations

import re
from collections import Counter
from typing import Any

from epistemic_case_mapper.map_briefing_memo_ready_packet_helpers import (
    dedupe as _dedupe,
    list_value as _list,
    norm as _norm,
    string_list as _string_list,
)


COMPARISON_CUES = (
    "compared with",
    "compared to",
    "rather than",
    "instead of",
    "alternative to",
    "replacement for",
    "substitute for",
    "more than",
    "less than",
)


def build_memo_polish_diagnostics(before: str, after: str, packet: dict[str, Any]) -> dict[str, Any]:
    unsupported = unsupported_addition_warnings(before, after, packet)
    prose = prose_quality_diagnostics(after)
    return {
        "schema_id": "memo_polish_diagnostics_v1",
        "status": "warning" if unsupported or prose.get("warning_count", 0) else "ready",
        "unsupported_addition_warnings": unsupported,
        "unsupported_addition_count": len(unsupported),
        "prose_quality": prose,
    }


def unsupported_addition_warnings(before: str, after: str, packet: dict[str, Any]) -> list[dict[str, Any]]:
    before_text = _norm(before)
    allowed_text = _norm(" ".join([before, _packet_text_surface(packet)]))
    allowed_terms = set(_content_terms(allowed_text))
    warnings = []
    for sentence in _sentences(after):
        sentence_norm = _norm(sentence)
        if not sentence_norm or sentence_norm in before_text:
            continue
        cues = [cue for cue in COMPARISON_CUES if cue in sentence_norm]
        if not cues:
            continue
        new_terms = [
            term
            for term in _content_terms(sentence)
            if not _term_supported_by_allowed_surface(term, allowed_text, allowed_terms)
            and not _allowed_new_term(term)
        ]
        if new_terms:
            warnings.append(
                {
                    "warning_type": "new_comparison_or_recommendation_surface",
                    "severity": "high" if len(new_terms) >= 2 else "moderate",
                    "cues": cues,
                    "new_terms": new_terms[:8],
                    "sentence": sentence,
                }
            )
    return warnings


def prose_quality_diagnostics(text: str) -> dict[str, Any]:
    sentences = _sentences(text)
    paragraphs = [p.strip() for p in re.split(r"\n\s*\n", str(text or "")) if p.strip()]
    repeated_starts = _repeated_sentence_starts(sentences)
    long_paragraphs = [
        {"paragraph_index": index + 1, "word_count": len(_words(paragraph))}
        for index, paragraph in enumerate(paragraphs)
        if len(_words(paragraph)) > 170
    ]
    citation_dense = [
        {"paragraph_index": index + 1, "citation_count": paragraph.count("[")}
        for index, paragraph in enumerate(paragraphs)
        if paragraph.count("[") >= 5
    ]
    unfinished = [
        {"paragraph_index": index + 1, "ending": paragraph[-80:]}
        for index, paragraph in enumerate(paragraphs)
        if _looks_unfinished(paragraph)
    ]
    warnings = []
    if repeated_starts:
        warnings.append("repeated_sentence_starts")
    if long_paragraphs:
        warnings.append("overlong_paragraphs")
    if citation_dense:
        warnings.append("citation_dense_paragraphs")
    if unfinished:
        warnings.append("unfinished_sentence_markers")
    return {
        "schema_id": "memo_prose_quality_diagnostics_v1",
        "status": "warning" if warnings else "ready",
        "warning_count": len(warnings),
        "warnings": warnings,
        "sentence_count": len(sentences),
        "paragraph_count": len(paragraphs),
        "repeated_sentence_starts": repeated_starts,
        "overlong_paragraphs": long_paragraphs,
        "citation_dense_paragraphs": citation_dense,
        "unfinished_sentence_markers": unfinished,
    }


def high_confidence_unsupported_additions(diagnostics: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        row
        for row in _list(diagnostics.get("unsupported_addition_warnings"))
        if isinstance(row, dict) and row.get("severity") == "high"
    ]


def _packet_text_surface(packet: dict[str, Any]) -> str:
    return " ".join(_text_leaves(packet))


def _text_leaves(value: Any) -> list[str]:
    if isinstance(value, str):
        return [value]
    if isinstance(value, (int, float, bool)):
        return [str(value)]
    if isinstance(value, dict):
        parts: list[str] = []
        for item in value.values():
            parts.extend(_text_leaves(item))
        return parts
    if isinstance(value, list):
        parts = []
        for item in value:
            parts.extend(_text_leaves(item))
        return parts
    return []


def _sentences(text: str) -> list[str]:
    without_headings = "\n".join(
        line for line in str(text or "").splitlines() if not line.lstrip().startswith("#")
    )
    cleaned = re.sub(r"\s+", " ", without_headings).strip()
    if not cleaned:
        return []
    return [row.strip() for row in re.split(r"(?<=[.!?])\s+(?=[A-Z0-9*])", cleaned) if row.strip()]


def _content_terms(text: str) -> list[str]:
    terms = [
        term
        for term in re.findall(r"[a-z][a-z0-9-]{3,}", str(text or "").lower())
        if term not in _STOPWORDS and not re.fullmatch(r"[a-z]*\d+[a-z]*", term)
    ]
    return _dedupe(terms)


def _allowed_new_term(term: str) -> bool:
    if term.startswith(("source", "section", "memo")):
        return True
    return term in {
        "analysis",
        "decision",
        "evidence",
        "interpretation",
        "pattern",
        "patterns",
        "prose",
        "reader",
        "reinforce",
        "reinforced",
        "reinforces",
        "reinforcing",
        "relationship",
        "relationships",
        "valid",
    }


def _term_supported_by_allowed_surface(term: str, allowed_text: str, allowed_terms: set[str]) -> bool:
    value = str(term or "").strip().lower()
    if not value:
        return True
    if value in allowed_text or value in allowed_terms:
        return True
    if _term_variants(value).intersection(allowed_terms):
        return True
    if "-" in value:
        parts = [part for part in value.split("-") if part]
        substantive_parts = [part for part in parts if part not in {"based", "level", "levels", "specific"}]
        if substantive_parts and all(_term_supported_by_allowed_surface(part, allowed_text, allowed_terms) for part in substantive_parts):
            return True
    return False


def _term_variants(term: str) -> set[str]:
    variants = {term}
    suffixes = (
        ("ies", "y"),
        ("ions", "e"),
        ("ion", "e"),
        ("tions", "t"),
        ("tion", "t"),
        ("ing", ""),
        ("ed", ""),
        ("es", ""),
        ("s", ""),
    )
    for suffix, replacement in suffixes:
        if term.endswith(suffix) and len(term) > len(suffix) + 3:
            variants.add(term[: -len(suffix)] + replacement)
            variants.add(term[: -len(suffix)])
    return {variant for variant in variants if len(variant) >= 4}


def _repeated_sentence_starts(sentences: list[str]) -> list[dict[str, Any]]:
    starts = [
        " ".join(_words(sentence)[:3]).lower()
        for sentence in sentences
        if len(_words(sentence)) >= 3
    ]
    counts = Counter(starts)
    return [
        {"start": start, "count": count}
        for start, count in sorted(counts.items())
        if count >= 3 and start
    ]


def _words(text: str) -> list[str]:
    return re.findall(r"[A-Za-z0-9][A-Za-z0-9'-]*", str(text or ""))


def _looks_unfinished(paragraph: str) -> bool:
    text = str(paragraph or "").rstrip()
    if not text:
        return False
    if text.endswith(("...", "…")):
        return True
    return bool(re.search(r"\b(?:and|or|but|because|with|without|including|such as|to|of|for|by|in)$", text, flags=re.IGNORECASE))


_STOPWORDS = {
    "about",
    "above",
    "across",
    "after",
    "also",
    "answer",
    "because",
    "before",
    "between",
    "could",
    "does",
    "from",
    "have",
    "into",
    "more",
    "rather",
    "should",
    "stays",
    "than",
    "that",
    "their",
    "there",
    "these",
    "this",
    "through",
    "when",
    "where",
    "while",
    "with",
    "would",
}
