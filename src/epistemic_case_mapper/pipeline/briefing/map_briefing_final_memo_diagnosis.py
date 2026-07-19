from __future__ import annotations

import re
from collections import Counter
from typing import Any

from epistemic_case_mapper.pipeline.briefing.map_briefing_markdown_quality import extraction_debris_issues, markdown_structure_issues
from epistemic_case_mapper.pipeline.briefing.map_briefing_section_role_quality import section_role_quality_report


SECTION_RE = re.compile(r"^##\s+(.+?)\s*$", flags=re.MULTILINE)
SENTENCE_RE = re.compile(r"[^.!?\n][^.!?\n]*(?:[.!?]|$)")
NUMBER_RE = re.compile(
    r"(?<![A-Za-z0-9_])(?:\d+(?:\.\d+)?%?|\d+\s*(?:-|to)\s*\d+|\b\d+/\d+\b)(?![A-Za-z0-9_])(?:\s*(?:mg|g|kg|ml|l|cm|mm|years?|months?|days?|weeks?|hours?|per\s+\w+))?",
    flags=re.IGNORECASE,
)
EVIDENCE_ID_RE = re.compile(r"\b(?:claim|relation|source|evidence)_[A-Za-z0-9_.:-]+\b|`[^`\n]*(?:claim|relation|source|evidence)[^`\n]*`", flags=re.IGNORECASE)
SOURCE_LABEL_RE = re.compile(r"\(([A-Z][A-Za-z0-9][A-Za-z0-9 .,&:/+-]{1,90})\)")
RAW_DIAGNOSTIC_RE = re.compile(
    r"\b(?:fail|warning|error|needs_review|missing_[a-z0-9_]+|[a-z]+(?:_[a-z0-9]+){2,})\b",
    flags=re.IGNORECASE,
)
RAW_STATUS_RE = re.compile(r"\b(?:fail|warning|error|needs_review)\s*:", flags=re.IGNORECASE)

COHERENCE_OPENING_MARKERS = (
    "the answer is context-dependent",
    "it depends",
    "practical application",
    "context",
    "however",
    "this analysis",
)
WEAK_OPENING_PHRASES = (
    "the current map supports",
    "current map supports",
    "the map supports",
    "under stated conditions read",
    "under the stated conditions read",
    "current read is",
)
INTERNAL_PROCESS_PHRASES = (
    "mapped support",
    "map-backed read",
    "decision role",
    "load-bearing map distinction",
    "preserved as a load-bearing map distinction",
    "not specified",
)
AWKWARD_PHRASES = (
    "awkward",
    "unclear",
    "clunky",
    "mechanical",
)
CAVEAT_MARKERS = (
    "except",
    "exception",
    "boundary",
    "condition",
    "conditional",
    "uncertain",
    "uncertainty",
    "missing",
    "limited",
    "limit",
    "subgroup",
    "separately",
    "caveat",
)


def build_memo_protected_spans(memo: str, contract: dict[str, Any] | None = None) -> dict[str, Any]:
    """Build prompt-visible and validator-visible spans that final editors preserve."""
    contract = contract or {}
    spans: list[dict[str, Any]] = []
    _add_section_heading_spans(spans, memo)
    _add_line_spans(spans, memo, kind="confidence_line", predicate=lambda line: line.strip().startswith("**Confidence:**"))
    question = str(contract.get("question", "")).strip()
    if question:
        _add_exact_spans(spans, memo, question, kind="decision_question", source="contract.question")
    _add_sources_section_spans(spans, memo)
    _add_regex_spans(spans, memo, NUMBER_RE, kind="quantity", source="number_pattern")
    _add_regex_spans(spans, memo, EVIDENCE_ID_RE, kind="evidence_identifier", source="identifier_pattern")
    _add_regex_spans(spans, memo, SOURCE_LABEL_RE, kind="source_label", source="parenthetical_source_label")
    return {
        "schema_id": "memo_protected_spans_v1",
        "span_count": len(spans),
        "spans": _dedupe_spans(spans),
        "rules": [
            "Preserve the decision question line exactly.",
            "Preserve section headings exactly.",
            "Preserve the confidence label exactly.",
            "Preserve source labels, source names, evidence identifiers, and the final source list exactly.",
            "Preserve numbers, measured quantities, confidence intervals, and dose/frequency thresholds exactly.",
            "Preserve uncertainty, missing-evidence, and bounded-answer wording.",
        ],
    }


def build_memo_final_diagnosis(memo: str, contract: dict[str, Any] | None = None) -> dict[str, Any]:
    """Diagnose final memo issues without using case-specific vocabulary."""
    contract = contract or {}
    sections = _sections(memo)
    sentences = _sentences(memo)
    repeated = _repeated_sentences(sentences)
    repeated_caveats = _repeated_caveat_terms(sentences)
    weak_opening = _weak_opening_issue(memo)
    section_openings = _awkward_section_openings(sections)
    long_sentences = _long_sentences(sentences)
    internal_phrases = _internal_phrase_issues(memo)
    awkward_phrases = _awkward_phrase_issues(memo)
    diagnostic_leakage = _diagnostic_leakage_issues(sections)
    structure_issues = markdown_structure_issues(memo)
    debris_issues = extraction_debris_issues(memo)
    dense_paragraphs = _dense_paragraph_issues(sections)
    role_quality = section_role_quality_report(memo, contract)
    raw_status_flags = _raw_status_flags(memo)
    question = str(contract.get("question", "")).strip()
    question_missing = bool(question and _normalize(question) not in _normalize(memo))
    coherence_issues: list[dict[str, Any]] = []
    if question_missing:
        coherence_issues.append({"kind": "decision_question_missing", "message": "Decision question is not visible in the memo."})
    if weak_opening:
        coherence_issues.append(weak_opening)
    if repeated:
        coherence_issues.append(
            {
                "kind": "repeated_sentences",
                "message": "Exact or near-exact sentences recur across the memo.",
                "items": repeated[:8],
            }
        )
    if repeated_caveats:
        coherence_issues.append(
            {
                "kind": "repeated_caveat_terms",
                "message": "Caveat language may be over-weighted across sections.",
                "items": repeated_caveats[:8],
            }
        )
    prose_issues: list[dict[str, Any]] = []
    if section_openings:
        prose_issues.append({"kind": "awkward_section_openings", "message": "Some sections open with weak transition language.", "items": section_openings[:8]})
    if long_sentences:
        prose_issues.append({"kind": "long_sentences", "message": "Some sentences are long enough to impair readability.", "items": long_sentences[:8]})
    if internal_phrases:
        prose_issues.append({"kind": "internal_process_language", "message": "Memo contains internal process phrasing.", "items": internal_phrases[:8]})
    if awkward_phrases:
        prose_issues.append({"kind": "awkward_language_markers", "message": "Memo contains language that explicitly signals awkwardness or unclear prose.", "items": awkward_phrases[:8]})
    if diagnostic_leakage:
        prose_issues.append(
            {
                "kind": "diagnostic_leakage",
                "message": "Reader-facing prose contains raw diagnostic/status language or machine identifiers.",
                "items": diagnostic_leakage[:8],
            }
        )
    if structure_issues:
        prose_issues.append(
            {
                "kind": "markdown_structure",
                "message": "Memo contains mechanically damaged Markdown structure.",
                "items": structure_issues[:8],
            }
        )
    if debris_issues:
        prose_issues.append(
            {
                "kind": "extraction_debris",
                "message": "Memo contains extraction debris that should stay out of reader-facing prose.",
                "items": debris_issues[:8],
            }
        )
    if dense_paragraphs:
        prose_issues.append(
            {
                "kind": "dense_paragraphs",
                "message": "Some paragraphs are dense enough to need local compression or splitting.",
                "items": dense_paragraphs[:8],
            }
        )
    if role_quality.get("issues"):
        prose_issues.append(
            {
                "kind": "section_role_quality",
                "message": "Some sections need cleaner decision-memo role discipline.",
                "items": role_quality.get("issues", [])[:8],
            }
        )
    return {
        "schema_id": "memo_final_diagnosis_v1",
        "metrics": {
            "word_count": len(memo.split()),
            "section_count": len(sections),
            "sentence_count": len(sentences),
            "repeated_sentence_count": len(repeated),
            "repeated_caveat_term_count": len(repeated_caveats),
            "long_sentence_count": len(long_sentences),
            "internal_phrase_count": len(internal_phrases),
            "awkward_phrase_count": len(awkward_phrases),
            "diagnostic_leakage_count": len(diagnostic_leakage),
            "markdown_structure_issue_count": len(structure_issues),
            "extraction_debris_issue_count": len(debris_issues),
            "raw_status_flag_count": len(raw_status_flags),
            "dense_paragraph_count": len(dense_paragraphs),
            "section_role_quality_issue_count": int(role_quality.get("issue_count", 0) or 0),
        },
        "coherence": {
            "status": "warning" if coherence_issues else "pass",
            "issue_count": len(coherence_issues),
            "issues": coherence_issues,
        },
        "prose": {
            "status": "warning" if prose_issues else "pass",
            "issue_count": len(prose_issues),
            "issues": prose_issues,
        },
        "section_role_quality": role_quality,
    }


def diagnosis_improved(before: dict[str, Any], after: dict[str, Any], *, pass_name: str) -> bool:
    """Return whether pass-specific diagnosis metrics moved in the right direction."""
    before_metrics = before.get("metrics", {}) if isinstance(before.get("metrics"), dict) else {}
    after_metrics = after.get("metrics", {}) if isinstance(after.get("metrics"), dict) else {}
    if pass_name == "coherence":
        keys = ("repeated_sentence_count", "repeated_caveat_term_count")
    elif pass_name == "prose":
        keys = (
            "long_sentence_count",
            "internal_phrase_count",
            "awkward_phrase_count",
            "diagnostic_leakage_count",
            "markdown_structure_issue_count",
            "extraction_debris_issue_count",
            "raw_status_flag_count",
            "dense_paragraph_count",
        )
    else:
        keys = (
            "repeated_sentence_count",
            "repeated_caveat_term_count",
            "long_sentence_count",
            "internal_phrase_count",
            "awkward_phrase_count",
            "diagnostic_leakage_count",
            "markdown_structure_issue_count",
            "extraction_debris_issue_count",
            "raw_status_flag_count",
            "dense_paragraph_count",
        )
    if any(_int(after_metrics.get(key)) < _int(before_metrics.get(key)) for key in keys):
        return True
    before_section = before.get(pass_name, {}) if isinstance(before.get(pass_name), dict) else {}
    after_section = after.get(pass_name, {}) if isinstance(after.get(pass_name), dict) else {}
    return _int(after_section.get("issue_count")) < _int(before_section.get("issue_count"))


def _add_section_heading_spans(spans: list[dict[str, Any]], memo: str) -> None:
    for match in SECTION_RE.finditer(memo):
        spans.append(_span(memo, match.start(), match.end(), kind="section_heading", source="markdown_heading"))


def _add_line_spans(spans: list[dict[str, Any]], memo: str, *, kind: str, predicate: Any) -> None:
    offset = 0
    for line in memo.splitlines(keepends=True):
        stripped = line.rstrip("\n")
        if predicate(stripped):
            spans.append(_span(memo, offset, offset + len(stripped), kind=kind, source="line_pattern"))
        offset += len(line)


def _add_sources_section_spans(spans: list[dict[str, Any]], memo: str) -> None:
    match = re.search(r"(?ms)^##\s+Sources\s*$.*?(?=^##\s+|\Z)", memo)
    if match:
        spans.append(_span(memo, match.start(), match.end(), kind="sources_section", source="sources_heading"))


def _add_exact_spans(spans: list[dict[str, Any]], memo: str, text: str, *, kind: str, source: str) -> None:
    start = 0
    while text and True:
        index = memo.find(text, start)
        if index < 0:
            break
        spans.append(_span(memo, index, index + len(text), kind=kind, source=source))
        start = index + len(text)


def _add_regex_spans(spans: list[dict[str, Any]], memo: str, pattern: re.Pattern[str], *, kind: str, source: str) -> None:
    for match in pattern.finditer(memo):
        text = match.group(0).strip()
        if len(text) < 2:
            continue
        spans.append(_span(memo, match.start(), match.end(), kind=kind, source=source))


def _span(memo: str, start: int, end: int, *, kind: str, source: str) -> dict[str, Any]:
    return {"kind": kind, "source": source, "start": start, "end": end, "text": memo[start:end]}


def _dedupe_spans(spans: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[tuple[str, int, int, str]] = set()
    deduped: list[dict[str, Any]] = []
    for span in sorted(spans, key=lambda item: (int(item["start"]), int(item["end"]), str(item["kind"]))):
        key = (str(span["kind"]), int(span["start"]), int(span["end"]), str(span["text"]))
        if key not in seen:
            seen.add(key)
            deduped.append(span)
    return deduped


def _sections(memo: str) -> list[dict[str, str]]:
    matches = list(SECTION_RE.finditer(memo))
    sections: list[dict[str, str]] = []
    for index, match in enumerate(matches):
        end = matches[index + 1].start() if index + 1 < len(matches) else len(memo)
        sections.append({"title": match.group(1).strip(), "markdown": memo[match.start():end].strip()})
    return sections


def _sentences(text: str) -> list[str]:
    sentences = [re.sub(r"\s+", " ", match.group(0)).strip() for match in SENTENCE_RE.finditer(text)]
    return [sentence for sentence in sentences if len(sentence.split()) >= 4 and not sentence.startswith("## ")]


def _repeated_sentences(sentences: list[str]) -> list[dict[str, Any]]:
    counts = Counter(_normalize(sentence) for sentence in sentences)
    originals = { _normalize(sentence): sentence for sentence in sentences }
    return [
        {"text": originals[key], "count": count}
        for key, count in counts.most_common()
        if count > 1 and len(key) > 30
    ]


def _repeated_caveat_terms(sentences: list[str]) -> list[dict[str, Any]]:
    counts: Counter[str] = Counter()
    examples: dict[str, str] = {}
    for sentence in sentences:
        lowered = sentence.lower()
        if not any(marker in lowered for marker in CAVEAT_MARKERS):
            continue
        for marker in CAVEAT_MARKERS:
            if marker in lowered:
                counts[marker] += 1
                examples.setdefault(marker, sentence)
    return [
        {"term": term, "count": count, "example": examples.get(term, "")}
        for term, count in counts.most_common()
        if count > 2
    ]


def _weak_opening_issue(memo: str) -> dict[str, Any] | None:
    first = _first_body_paragraph(memo).lower()
    if not first:
        return {"kind": "missing_opening_answer", "message": "Memo lacks a clear opening answer paragraph."}
    if any(first.startswith(marker) for marker in COHERENCE_OPENING_MARKERS):
        return {"kind": "weak_opening_answer", "message": "Opening answer starts with caveat or transition language.", "text": _first_body_paragraph(memo)}
    if any(phrase in first for phrase in WEAK_OPENING_PHRASES):
        return {"kind": "weak_opening_answer", "message": "Opening answer uses map-process language instead of a direct reader-facing answer.", "text": _first_body_paragraph(memo)}
    return None


def _first_body_paragraph(memo: str) -> str:
    for part in re.split(r"\n\s*\n", memo):
        stripped = part.strip()
        if not stripped or stripped.startswith("#") or stripped.startswith("**Confidence:**"):
            continue
        return re.sub(r"\s+", " ", stripped)
    return ""


def _awkward_section_openings(sections: list[dict[str, str]]) -> list[dict[str, str]]:
    issues: list[dict[str, str]] = []
    for section in sections:
        body = section["markdown"].split("\n", 1)[1] if "\n" in section["markdown"] else ""
        opening = _first_body_paragraph(body)
        if opening and any(opening.lower().startswith(marker) for marker in COHERENCE_OPENING_MARKERS):
            issues.append({"section": section["title"], "text": opening})
    return issues


def _long_sentences(sentences: list[str]) -> list[dict[str, Any]]:
    return [
        {"word_count": len(sentence.split()), "text": sentence}
        for sentence in sentences
        if len(sentence.split()) > 32
    ]


def _internal_phrase_issues(memo: str) -> list[dict[str, str]]:
    lowered = memo.lower()
    return [
        {"phrase": phrase}
        for phrase in INTERNAL_PROCESS_PHRASES
        if phrase in lowered
    ]


def _awkward_phrase_issues(memo: str) -> list[dict[str, str]]:
    lowered = memo.lower()
    return [{"phrase": phrase} for phrase in AWKWARD_PHRASES if phrase in lowered]


def _diagnostic_leakage_issues(sections: list[dict[str, str]]) -> list[dict[str, Any]]:
    issues: list[dict[str, Any]] = []
    for section in sections:
        for paragraph in _paragraphs(section["markdown"]):
            matches = [match.group(0) for match in RAW_DIAGNOSTIC_RE.finditer(paragraph)]
            if not matches:
                continue
            if _paragraph_is_protected_reference(paragraph):
                continue
            issues.append(
                {
                    "section": section["title"],
                    "matches": list(dict.fromkeys(matches))[:8],
                    "text": _short_text(paragraph, 700),
                }
            )
    return issues


def _raw_status_flags(memo: str) -> list[str]:
    return [match.group(0) for match in RAW_STATUS_RE.finditer(memo)]


def _dense_paragraph_issues(sections: list[dict[str, str]]) -> list[dict[str, Any]]:
    issues: list[dict[str, Any]] = []
    for section in sections:
        if section["title"].strip().lower() in {"sources", "evidence trail"}:
            continue
        for paragraph in _paragraphs(section["markdown"]):
            words = paragraph.split()
            if len(words) <= 55:
                continue
            if paragraph.startswith("|") or paragraph.startswith("- "):
                continue
            issues.append({"section": section["title"], "word_count": len(words), "text": _short_text(paragraph, 700)})
    return issues


def _paragraphs(markdown: str) -> list[str]:
    values = []
    for paragraph in re.split(r"\n\s*\n", markdown):
        cleaned = re.sub(r"\s+", " ", paragraph).strip()
        if cleaned and not cleaned.startswith("## ") and not cleaned.startswith("**Confidence:**"):
            values.append(cleaned)
    return values


def _paragraph_is_protected_reference(paragraph: str) -> bool:
    lowered = paragraph.lower()
    return paragraph.startswith("- ") or lowered.startswith("the structured evidence trail")


def _short_text(text: str, max_chars: int) -> str:
    compact = re.sub(r"\s+", " ", text).strip()
    if len(compact) <= max_chars:
        return compact
    return compact[: max_chars - 3].rstrip() + "..."


def _normalize(text: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9]+", " ", text.lower())).strip()


def _int(value: Any) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0
