from __future__ import annotations

import json
import re
from copy import deepcopy
from typing import Any

from epistemic_case_mapper.model_backends import run_model_backend
from epistemic_case_mapper.synthesis_uplift_packet import _parse_json


def run_reader_packet_verbalization(
    reader_packet: dict[str, Any],
    *,
    backend: str,
    backend_timeout: int | None,
    backend_retries: int,
) -> dict[str, Any]:
    """Make reader-packet evidence cards prose-ready before memo synthesis."""

    prompt = build_reader_packet_verbalization_prompt(reader_packet)
    report: dict[str, Any] = {
        "schema_id": "reader_packet_verbalization_report_v1",
        "status": "not_run",
        "accepted_count": 0,
        "rejected_count": 0,
        "issues": [],
        "accepted": [],
        "rejected": [],
    }
    if backend.strip() == "prompt":
        report.update({"status": "skipped_prompt_backend", "issues": ["prompt backend does not run verbalization"]})
        return {"reader_packet": reader_packet, "prompt": prompt, "raw": "", "report": report}
    try:
        result = run_model_backend(prompt, backend, timeout_seconds=backend_timeout, max_retries=backend_retries)
    except RuntimeError as exc:
        report.update({"status": "backend_error_kept_original", "issues": [str(exc)]})
        return {"reader_packet": reader_packet, "prompt": prompt, "raw": "", "report": report}
    raw = result.text
    if result.prompt_only:
        report.update({"status": "prompt_backend_kept_original", "issues": ["verbalization backend returned prompt only"]})
        return {"reader_packet": reader_packet, "prompt": prompt, "raw": raw, "report": report}
    payload = _parse_json(raw)
    if not isinstance(payload, dict):
        report.update({"status": "parse_failed_kept_original", "issues": ["verbalization response was not a JSON object"]})
        return {"reader_packet": reader_packet, "prompt": prompt, "raw": raw, "report": report}
    verbalized, accepted, rejected = apply_reader_packet_verbalizations(reader_packet, payload)
    report.update(
        {
            "status": "accepted" if accepted else "no_valid_verbalizations_kept_original",
            "accepted_count": len(accepted),
            "rejected_count": len(rejected),
            "accepted": accepted,
            "rejected": rejected,
            "issues": [] if accepted else ["no proposed verbalizations passed validation"],
        }
    )
    return {"reader_packet": verbalized, "prompt": prompt, "raw": raw, "report": report}


def build_reader_packet_verbalization_prompt(reader_packet: dict[str, Any]) -> str:
    cards = _model_cards(reader_packet)
    return (
        "You are improving evidence-card wording before a decision memo is synthesized.\n"
        "Rewrite each supplied evidence card as one natural, source-grounded sentence.\n\n"
        "Rules:\n"
        "- Return only valid JSON.\n"
        "- Preserve every protected number for that card exactly.\n"
        "- Include one bracketed source label from that card's accepted_source_labels.\n"
        "- Prefer the simplest readable accepted source label; it will be canonicalized after validation.\n"
        "- Do not add new numbers, sources, examples, populations, causal claims, or recommendations.\n"
        "- Do not mention card IDs, packet schema, validation, repair, or internal pipeline status in the sentence.\n"
        "- Keep each sentence concise and useful for a decision memo.\n"
        "- If a card is already clear, return a lightly cleaned version.\n\n"
        "Return schema:\n"
        "{\n"
        '  "verbalizations": [\n'
        '    {"card_id": "card id from input", "sentence": "one natural sentence with [accepted source label]"}\n'
        "  ]\n"
        "}\n\n"
        "Evidence cards:\n"
        f"{json.dumps(cards, indent=2, ensure_ascii=False)}\n"
    )


def apply_reader_packet_verbalizations(
    reader_packet: dict[str, Any],
    payload: dict[str, Any],
) -> tuple[dict[str, Any], list[dict[str, Any]], list[dict[str, Any]]]:
    proposed_rows = payload.get("verbalizations")
    if not isinstance(proposed_rows, list):
        proposed_rows = payload.get("sentences")
    if not isinstance(proposed_rows, list):
        proposed_rows = []
    proposed = {
        str(row.get("card_id") or "").strip(): str(row.get("sentence") or "").strip()
        for row in proposed_rows
        if isinstance(row, dict) and str(row.get("card_id") or "").strip()
    }
    packet = deepcopy(reader_packet)
    accepted: list[dict[str, Any]] = []
    rejected: list[dict[str, Any]] = []
    for section, index, card in _iter_cards(packet):
        card_id = str(card.get("card_id") or "").strip()
        sentence = proposed.get(card_id, "")
        if not sentence:
            continue
        issues = _verbalization_issues(sentence, card)
        if issues:
            rejected.append({"card_id": card_id, "section": section, "issues": issues, "sentence": sentence})
            continue
        source = str(card.get("source") or "").strip()
        card["prose"] = canonicalize_source_aliases(_clean_sentence(sentence), [source] if source else [])
        accepted.append({"card_id": card_id, "section": section, "canonicalized_source": bool(source)})
    return packet, accepted, rejected


def _model_cards(reader_packet: dict[str, Any]) -> list[dict[str, Any]]:
    cards = []
    for section, _index, card in _iter_cards(reader_packet):
        card_id = str(card.get("card_id") or "").strip()
        statement = str(card.get("statement") or "").strip()
        source = str(card.get("source") or "").strip()
        if not card_id or not statement or not source:
            continue
        cards.append(
            {
                "card_id": card_id,
                "section": section,
                "role": card.get("role"),
                "statement": statement,
                "source_label": source,
                "accepted_source_labels": source_aliases_for_label(source),
                "protected_numbers": _protected_numbers(card),
                "interpretation": card.get("interpretation"),
                "limits": card.get("limits", []),
            }
        )
    return cards[:18]


def _iter_cards(reader_packet: dict[str, Any]):
    for section in ("evidence_cards", "counterweight_cards", "decision_cruxes", "quantitative_anchors"):
        rows = reader_packet.get(section, []) if isinstance(reader_packet.get(section), list) else []
        for index, card in enumerate(rows):
            if isinstance(card, dict):
                yield section, index, card


def _verbalization_issues(sentence: str, card: dict[str, Any]) -> list[str]:
    cleaned = _clean_sentence(sentence)
    issues = []
    if not cleaned:
        return ["empty sentence"]
    if _has_internal_markers(cleaned):
        issues.append("contains internal marker")
    source = str(card.get("source") or "").strip()
    if source and not _contains_source_alias(cleaned, source):
        issues.append("missing accepted bracketed source label")
    for number in _protected_numbers(card):
        if number not in cleaned:
            issues.append(f"missing protected number: {number}")
    allowed_numbers = (
        set(_protected_numbers(card))
        | set(_number_tokens(str(card.get("statement") or "")))
        | set(_number_tokens(str(card.get("source") or "")))
        | set(_number_tokens(" ".join(source_aliases_for_label(str(card.get("source") or "")))))
    )
    for number in _number_tokens(cleaned):
        if number not in allowed_numbers:
            issues.append(f"introduced unsupported number: {number}")
    if not _mentions_enough_content_terms(cleaned, str(card.get("statement") or ""), minimum=3):
        issues.append("does not preserve enough statement content")
    return issues


def _protected_numbers(card: dict[str, Any]) -> list[str]:
    values = _string_list(card.get("quantities"))
    if values:
        return _dedupe(_number_tokens(" ".join(values[:3])))
    return _dedupe(_number_tokens(str(card.get("statement") or "")))


def source_aliases_for_label(label: str) -> list[str]:
    """Return packet-derived source aliases that are safe to canonicalize."""

    source = _clean_sentence(label)
    if not source:
        return []
    year = _source_year(source)
    aliases = [source]
    without_suffix = re.sub(r"\s+\b(?:Fullish|Full|Abstract|Metadata|Pubmed|PMC)\b$", "", source, flags=re.IGNORECASE).strip()
    if without_suffix:
        aliases.append(without_suffix)
    compact = re.sub(r"\s+et\s+al\.?", "", without_suffix, flags=re.IGNORECASE).strip()
    if compact:
        aliases.append(compact)
    if year:
        before_year = source[: source.rfind(year)].strip(" ,;:-")
        authorish = re.split(r";|,", before_year, maxsplit=1)[0].strip()
        authorish = re.sub(r"\s+et\s+al\.?$", "", authorish, flags=re.IGNORECASE).strip()
        if authorish:
            aliases.append(f"{authorish} {year}".strip())
        words = _source_alias_words(before_year)
        if words:
            aliases.append(f"{' '.join(words[:3])} {year}".strip())
            if len(words) >= 2:
                aliases.append(f"{' '.join(words[:2])} {year}".strip())
            aliases.append(f"{words[0]} {year}".strip())
            acronym = "".join(word[0].upper() for word in words[:4] if word)
            if len(acronym) >= 2:
                aliases.append(f"{acronym} {year}".strip())
    return _dedupe([alias for alias in aliases if alias])


def canonicalize_source_aliases(text: str, source_labels: list[str]) -> str:
    cleaned = str(text)
    replacements: list[tuple[str, str]] = []
    for label in source_labels:
        canonical = _clean_sentence(label)
        if not canonical:
            continue
        for alias in source_aliases_for_label(canonical):
            if alias != canonical:
                replacements.append((alias, canonical))
    for alias, canonical in sorted(replacements, key=lambda item: len(item[0]), reverse=True):
        cleaned = re.sub(rf"\[{re.escape(alias)}\]", f"[{canonical}]", cleaned)
    return _clean_sentence(cleaned)


def canonicalize_reader_packet_source_aliases(text: str, reader_packet: dict[str, Any]) -> str:
    labels: list[str] = []
    for _section, _index, card in _iter_cards(reader_packet):
        labels.extend(_string_list(card.get("source")))
    source_trail = reader_packet.get("source_trail", []) if isinstance(reader_packet.get("source_trail"), list) else []
    for row in source_trail:
        if isinstance(row, dict):
            labels.extend(_string_list(row.get("source")))
    return canonicalize_source_aliases(text, _dedupe(labels))


def _contains_source_alias(text: str, source: str) -> bool:
    return any(f"[{alias}]" in text for alias in source_aliases_for_label(source))


def _source_year(text: str) -> str:
    matches = re.findall(r"\b(?:19|20)\d{2}\b", text)
    return matches[-1] if matches else ""


def _source_alias_words(text: str) -> list[str]:
    stop = {
        "and",
        "authors",
        "evidence",
        "from",
        "group",
        "review",
        "study",
        "the",
        "with",
    }
    words: list[str] = []
    for word in re.findall(r"[A-Za-z][A-Za-z-]{1,}", text):
        cleaned = word.strip("-")
        if cleaned.lower() in stop or cleaned.lower() in {"et", "al"}:
            continue
        if cleaned not in words:
            words.append(cleaned)
    return words[:6]


def _has_internal_markers(text: str) -> bool:
    markers = ("bundle_", "retain_", "required_terms", "synthesis_suppressed", "Appendix-only extraction", "Map quality status")
    return any(marker in text for marker in markers)


def _mentions_enough_content_terms(text: str, statement: str, *, minimum: int) -> bool:
    terms = _content_terms(statement)
    if not terms:
        return True
    required = min(minimum, len(terms))
    lowered = text.lower()
    return sum(1 for term in terms if term in lowered) >= required


def _content_terms(text: str) -> list[str]:
    stop = {
        "about",
        "after",
        "again",
        "also",
        "because",
        "before",
        "between",
        "could",
        "current",
        "decision",
        "does",
        "from",
        "have",
        "into",
        "more",
        "should",
        "source",
        "that",
        "their",
        "there",
        "this",
        "those",
        "under",
        "when",
        "where",
        "which",
        "while",
        "with",
        "would",
    }
    terms = []
    for term in re.findall(r"[a-z0-9][a-z0-9-]{2,}", text.lower()):
        if term not in stop and term not in terms:
            terms.append(term)
    return terms


def _number_tokens(text: str) -> list[str]:
    return re.findall(r"\$?\d+(?:\.\d+)?%?", text)


def _string_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    text = str(value).strip()
    return [text] if text else []


def _dedupe(items: list[str]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for item in items:
        key = str(item).strip().lower()
        if not key or key in seen:
            continue
        seen.add(key)
        result.append(str(item).strip())
    return result


def _clean_sentence(text: str) -> str:
    cleaned = re.sub(r"\s+", " ", str(text)).strip()
    return cleaned
