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
            if term not in allowed_text and not _allowed_new_term(term)
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
    warnings = []
    if repeated_starts:
        warnings.append("repeated_sentence_starts")
    if long_paragraphs:
        warnings.append("overlong_paragraphs")
    if citation_dense:
        warnings.append("citation_dense_paragraphs")
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
    }


def high_confidence_unsupported_additions(diagnostics: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        row
        for row in _list(diagnostics.get("unsupported_addition_warnings"))
        if isinstance(row, dict) and row.get("severity") == "high"
    ]


def _packet_text_surface(packet: dict[str, Any]) -> str:
    parts: list[str] = []
    for key in ("decision_question", "answer_spine", "memo_obligations", "evidence_items", "source_trail"):
        parts.append(str(packet.get(key) or ""))
    return " ".join(parts)


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
    return term in {"decision", "evidence", "analysis", "reader", "prose"}


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
    "should",
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
