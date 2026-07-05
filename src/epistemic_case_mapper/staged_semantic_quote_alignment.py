from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class QuoteAlignment:
    span_id: str
    status: str
    method: str
    matched_text: str
    proposed_span_id: str
    quote: str
    coverage: float
    density: float


def align_source_quote_to_span(
    *,
    source_quote: str,
    proposed_span_id: str,
    span_lookup: dict[str, Any],
) -> QuoteAlignment | None:
    quote = _clean_quote(source_quote)
    proposed = str(proposed_span_id or "").strip()
    if not quote:
        if proposed in span_lookup:
            span = span_lookup[proposed]
            return QuoteAlignment(
                span_id=proposed,
                status="missing_quote_used_model_span",
                method="model_span_fallback",
                matched_text=str(getattr(span, "text", "")),
                proposed_span_id=proposed,
                quote="",
                coverage=0.0,
                density=0.0,
            )
        return None

    exact = _exact_quote_match(quote, span_lookup)
    if exact is not None:
        return _alignment_from_match(exact, quote, proposed, "exact_match")

    normalized = _normalized_quote_match(quote, span_lookup)
    if normalized is not None:
        return _alignment_from_match(normalized, quote, proposed, "normalized_match")

    fuzzy = _fuzzy_quote_match(quote, span_lookup)
    if fuzzy is not None:
        span_id, matched_text, coverage, density = fuzzy
        return QuoteAlignment(
            span_id=span_id,
            status=_status_for_span(span_id, proposed, "fuzzy_match"),
            method="fuzzy_token_overlap",
            matched_text=matched_text,
            proposed_span_id=proposed,
            quote=quote,
            coverage=coverage,
            density=density,
        )
    return None


def quote_alignment_metadata(alignment: QuoteAlignment) -> dict[str, Any]:
    return {
        "status": alignment.status,
        "method": alignment.method,
        "source_quote": alignment.quote,
        "matched_text": alignment.matched_text,
        "proposed_span_id": alignment.proposed_span_id,
        "resolved_span_id": alignment.span_id,
        "coverage": round(alignment.coverage, 3),
        "density": round(alignment.density, 3),
    }


def _alignment_from_match(match: tuple[str, str, float, float], quote: str, proposed: str, method: str) -> QuoteAlignment:
    span_id, matched_text, coverage, density = match
    return QuoteAlignment(
        span_id=span_id,
        status=_status_for_span(span_id, proposed, method),
        method=method,
        matched_text=matched_text,
        proposed_span_id=proposed,
        quote=quote,
        coverage=coverage,
        density=density,
    )


def _status_for_span(span_id: str, proposed_span_id: str, method: str) -> str:
    if proposed_span_id and span_id != proposed_span_id:
        return f"{method}_span_id_overridden"
    return method


def _exact_quote_match(quote: str, span_lookup: dict[str, Any]) -> tuple[str, str, float, float] | None:
    matches = []
    for span_id, span in span_lookup.items():
        text = str(getattr(span, "text", ""))
        if quote in text:
            matches.append((str(span_id), quote, 1.0, _density(quote, text)))
    return _best_match(matches)


def _normalized_quote_match(quote: str, span_lookup: dict[str, Any]) -> tuple[str, str, float, float] | None:
    normalized_quote = _normalize_space(quote)
    matches = []
    for span_id, span in span_lookup.items():
        text = str(getattr(span, "text", ""))
        if normalized_quote and normalized_quote in _normalize_space(text):
            matches.append((str(span_id), quote, 1.0, _density(quote, text)))
    return _best_match(matches)


def _fuzzy_quote_match(quote: str, span_lookup: dict[str, Any]) -> tuple[str, str, float, float] | None:
    quote_terms = _content_terms(quote)
    if len(quote_terms) < 4:
        return None
    matches = []
    quote_set = set(quote_terms)
    for span_id, span in span_lookup.items():
        text = str(getattr(span, "text", ""))
        span_terms = _content_terms(text)
        if not span_terms:
            continue
        overlap = sum(1 for term in quote_terms if term in set(span_terms))
        coverage = overlap / len(quote_terms)
        density = overlap / max(1, len(span_terms))
        if coverage >= 0.8 and density >= 0.2:
            matches.append((str(span_id), text, coverage, density))
    return _best_match(matches)


def _best_match(matches: list[tuple[str, str, float, float]]) -> tuple[str, str, float, float] | None:
    if not matches:
        return None
    return max(matches, key=lambda item: (item[2], item[3], -len(item[1]), item[0]))


def _clean_quote(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "").strip().strip('"').strip("'")).strip()


def _normalize_space(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def _content_terms(text: str) -> list[str]:
    return [term for term in re.findall(r"[a-z0-9]{3,}", text.lower()) if term not in _STOPWORDS]


def _density(quote: str, text: str) -> float:
    quote_terms = _content_terms(quote)
    text_terms = _content_terms(text)
    if not quote_terms or not text_terms:
        return 0.0
    return min(1.0, len(quote_terms) / len(text_terms))


_STOPWORDS = {
    "the",
    "and",
    "for",
    "that",
    "with",
    "from",
    "this",
    "were",
    "was",
    "are",
    "have",
    "has",
    "had",
    "not",
    "but",
    "between",
    "among",
}
